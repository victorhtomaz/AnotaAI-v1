import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from ollama import ResponseError

from anotai.domain.entities import UnidadeDocumento
from anotai.domain.exceptions import ErroAnaliseVisual

logger = logging.getLogger(__name__)

TIPOS_CLASSIFICACAO_IMAGEM = {"conteudo", "decorativo"}
MAPA_CLASSIFICACAO_IMAGEM = {
    "conteudo": "conteudo",
    "conteúdo": "conteudo",
    "content": "conteudo",
    "decorativo": "decorativo",
    "decorativa": "decorativo",
    "decorative": "decorativo",
}
TIPOS_UNIDADE_VISUAL = tuple(sorted(UnidadeDocumento.TIPOS_VISUAIS_VALIDOS))
MAPA_TIPOS_UNIDADE_VISUAL = {
    "figure": "figure",
    "figura": "figure",
    "image": "figure",
    "imagem": "figure",
    "diagram": "figure",
    "diagrama": "figure",
    "flowchart": "figure",
    "fluxograma": "figure",
    "photo": "figure",
    "foto": "figure",
    "fotografia": "figure",
    "illustration": "figure",
    "ilustracao": "figure",
    "ilustração": "figure",
    "map": "figure",
    "mapa": "figure",
    "table": "table",
    "tabela": "table",
    "quadro": "table",
    "graph": "graph",
    "grafico": "graph",
    "gráfico": "graph",
    "chart": "graph",
    "plot": "graph",
    "formula": "formula",
    "fórmula": "formula",
    "equation": "formula",
    "equacao": "formula",
    "equação": "formula",
}
CHAVES_TEXTO_UNIDADE = (
    "text",
    "texto",
    "texto_ocr",
    "ocr",
    "transcricao",
    "transcrição",
    "descricao",
    "description",
    "resumo",
    "summary",
    "content",
    "conteudo",
)
PROMPT_ANALISE_VISUAL_PADRAO = f"""Analise a imagem de material didático (especialmente slides) \
e retorne somente um JSON válido, sem markdown nem comentários:
{{"tipo": "conteudo" | "decorativo", "units": [{{"type": "<tipo>", "text": "<descrição>"}}]}}

CLASSIFICAÇÃO
- "conteudo" é o padrão: fotos, ilustrações, mapas, diagramas, esquemas, gráficos, fórmulas, \
tabelas, slides e imagens de documentos. Na dúvida, use "conteudo".
- Slides e documentos são SEMPRE "conteudo". Um slide com texto nunca é "decorativo", mesmo com \
logotipo ou fundo estilizado.
- "decorativo" apenas para logotipo isolado, ícone de interface ou borda/mancha abstrata sem \
relação com a aula. Nesse caso, "units" = [].

UNIDADES
- "type" deve ser um de: {", ".join(TIPOS_UNIDADE_VISUAL)}.
- Slides e documentos: uma única unidade "figure" para a imagem inteira, mesmo que contenha \
tabelas, gráficos ou fórmulas.
- Demais imagens: "figure" (fotos, mapas, diagramas, ilustrações), "table", "graph", "formula"; \
uma unidade por elemento distinto.

DESCRIÇÃO ("text")
- Em português, técnica, objetiva e autossuficiente, com no máximo 5 frases.
- Use o texto da imagem (título, tópicos, legendas, rótulos, eixos, valores) como contexto e \
mantenha os termos técnicos como aparecem. Sintetize; não transcreva blocos de texto.
- Slide: informe título, assunto principal, ideias-chave e os elementos visuais (diagrama, \
gráfico, foto) e como se relacionam ao texto.
- Descreva só o que está visível. Não invente nem complete texto ilegível, e não acrescente \
conhecimento externo.

Exemplo de saída: {{"tipo": "conteudo", "units": [{{"type": "figure", \
"text": "<síntese objetiva apenas do que está visível nesta imagem>"}}]}}"""


class ClienteOllama(Protocol):
    def chat(self, **kwargs: Any) -> Any: ...

    def show(self, **kwargs: Any) -> Any: ...


@dataclass
class AnalisadorVisualOllama:
    cliente: ClienteOllama
    modelo: str = "qwen3-vl:8b"
    prompt: str = PROMPT_ANALISE_VISUAL_PADRAO
    temperatura: float = 0.0
    seed: int = 42
    pensar: bool = False
    manter_vivo: str | int | float = "5m"

    def validar_modelo_visual(self) -> None:
        try:
            resposta = self.cliente.show(model=self.modelo)
        except (OSError, ResponseError, TimeoutError) as exc:
            raise ErroAnaliseVisual(
                f"não foi possível validar o modelo visual {self.modelo}"
            ) from exc
        if isinstance(resposta, dict):
            capacidades = resposta.get("capabilities", [])
            detalhes = resposta.get("details", {})
            familias = detalhes.get("families", []) if isinstance(detalhes, dict) else []
        else:
            capacidades = getattr(resposta, "capabilities", [])
            detalhes = getattr(resposta, "details", None)
            familias = getattr(detalhes, "families", []) if detalhes else []
        texto_capacidades = " ".join(map(str, capacidades + familias)).lower()
        if "vision" not in texto_capacidades and "clip" not in texto_capacidades:
            raise ErroAnaliseVisual(f"modelo {self.modelo} não declara capacidade visual/OCR")

    def analisar(self, imagem: bytes, numero_pagina: int) -> list[dict[str, Any]]:
        if not imagem:
            raise ErroAnaliseVisual("imagem da página vazia")
        try:
            resposta = self.cliente.chat(
                model=self.modelo,
                messages=[
                    {
                        "role": "user",
                        "content": self.prompt,
                        "images": [imagem],
                    }
                ],
                format="json",
                options={"temperature": self.temperatura, "seed": self.seed},
                think=self.pensar,
                keep_alive=self.manter_vivo,
            )
        except (OSError, ResponseError, TimeoutError) as exc:
            logger.warning(
                "Falha ao consultar Ollama no elemento da página %s; "
                "continuando sem unidades OCR: %s",
                numero_pagina,
                exc,
            )
            return []
        conteudo = self._extrair_conteudo_mensagem(resposta)
        try:
            dados = self._interpretar_resposta(conteudo)
        except ErroAnaliseVisual as exc:
            logger.warning(
                "Resposta inválida do Ollama no elemento da página %s; "
                "continuando sem unidades OCR: %s",
                numero_pagina,
                exc,
            )
            return []
        return self.normalizar_dados_visuais(dados, numero_pagina)

    @classmethod
    def normalizar_dados_visuais(
        cls,
        dados: dict[str, Any],
        numero_pagina: int,
        *,
        provedor_nome: str = "Ollama",
    ) -> list[dict[str, Any]]:
        tipo_imagem = cls._normalizar_classificacao_imagem(dados.get("tipo", "conteudo"))
        if tipo_imagem not in TIPOS_CLASSIFICACAO_IMAGEM:
            logger.warning(
                "Tipo visual inválido do %s na página %s; continuando sem unidades OCR",
                provedor_nome,
                numero_pagina,
            )
            return []
        unidades = dados.get("units")
        campos_raiz = {
            chave: dados.get(chave)
            for chave in CHAVES_TEXTO_UNIDADE
            if isinstance(dados.get(chave), str) and str(dados.get(chave)).strip()
        }
        tem_campos_raiz = bool(campos_raiz)
        tipo_raiz = cls._normalizar_tipo_unidade(dados.get("type")) or "figure"
        if not isinstance(unidades, list):
            if tem_campos_raiz or any(chave in dados for chave in CHAVES_TEXTO_UNIDADE):
                unidades = [{"type": tipo_raiz, **campos_raiz}]
            else:
                logger.warning(
                    "Resposta do %s sem units na página %s; continuando sem unidades OCR",
                    provedor_nome,
                    numero_pagina,
                )
                return []
        elif not unidades and tem_campos_raiz:
            unidades = [{"type": tipo_raiz, **campos_raiz}]
        resultado: list[dict[str, Any]] = []
        for unidade in unidades:
            if not isinstance(unidade, dict):
                continue
            tipo_bruto = unidade.get("type") or unidade.get("tipo")
            tipo_unidade = cls._normalizar_tipo_unidade(tipo_bruto)
            if tipo_unidade not in UnidadeDocumento.TIPOS_VISUAIS_VALIDOS:
                logger.warning(
                    "Tipo de unidade visual inválido na página %s: %s",
                    numero_pagina,
                    tipo_bruto,
                )
                continue
            unidade_enriquecida = (
                {
                    **campos_raiz,
                    **unidade,
                }
                if len(unidades) == 1 and tem_campos_raiz
                else unidade
            )
            texto_extraido = cls._extrair_texto_unidade(unidade_enriquecida)
            resultado.append(
                {
                    **unidade,
                    "type": tipo_unidade,
                    "text": texto_extraido,
                    "image_classification": tipo_imagem,
                }
            )
        if not resultado and tipo_imagem == "decorativo" and not unidades:
            return [{"type": "figure", "text": None, "image_classification": "decorativo"}]
        return resultado

    @staticmethod
    def _normalizar_classificacao_imagem(valor: Any) -> str | None:
        if not isinstance(valor, str):
            return None
        chave = valor.strip().lower()
        return MAPA_CLASSIFICACAO_IMAGEM.get(chave, chave)

    @staticmethod
    def _normalizar_tipo_unidade(valor: Any) -> str | None:
        if not isinstance(valor, str):
            return None
        chave = valor.strip().lower()
        return MAPA_TIPOS_UNIDADE_VISUAL.get(chave, chave)

    @staticmethod
    def _extrair_texto_unidade(unidade: dict[str, Any]) -> str | None:
        partes: list[str] = []
        for chave in CHAVES_TEXTO_UNIDADE:
            valor = unidade.get(chave)
            if isinstance(valor, str) and valor.strip() and valor.strip() not in partes:
                partes.append(valor.strip())
        return " - ".join(partes) if partes else None

    @staticmethod
    def _extrair_conteudo_mensagem(resposta: Any) -> str:
        mensagem = getattr(resposta, "message", None)
        if mensagem is not None:
            conteudo = getattr(mensagem, "content", None)
            if conteudo:
                return str(conteudo)
            pensamento = getattr(mensagem, "thinking", None)
            if pensamento:
                return str(pensamento)
        if isinstance(resposta, dict):
            mensagem = resposta.get("message")
            if isinstance(mensagem, dict):
                conteudo = mensagem.get("content") or mensagem.get("thinking")
                if conteudo:
                    return str(conteudo)
            if "response" in resposta:
                return str(resposta.get("response") or "")
        return ""

    @staticmethod
    def _interpretar_resposta(conteudo_bruto: str) -> dict[str, Any]:
        texto = (conteudo_bruto or "").strip()
        if not texto:
            raise ErroAnaliseVisual("resposta do Ollama vazia")
        if texto.startswith("```"):
            linhas = texto.splitlines()
            texto = "\n".join(
                linha for linha in linhas if not linha.strip().startswith("```")
            ).strip()
            if texto.lower().startswith("json"):
                texto = texto[4:].lstrip()
        candidatos = [texto]
        decodificador = json.JSONDecoder()
        for indice, caractere in enumerate(texto):
            if caractere != "{":
                continue
            try:
                candidato, _ = decodificador.raw_decode(texto[indice:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidato, dict):
                candidatos.append(json.dumps(candidato))
                break
        for candidato in candidatos:
            try:
                dados = json.loads(candidato)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(dados, dict):
                return dados
        raise ErroAnaliseVisual("resposta do Ollama não é JSON válido")
