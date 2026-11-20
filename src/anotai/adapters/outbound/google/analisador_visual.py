from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from anotai.adapters.outbound.ollama.analisador_visual import (
    PROMPT_ANALISE_VISUAL_PADRAO,
    AnalisadorVisualOllama,
)
from anotai.domain.exceptions import ErroAnaliseVisual

logger = logging.getLogger(__name__)

MODELO_PADRAO_GEMMA_VISUAL = "gemma-4-31b-it"
MODELOS_FALLBACK_PADRAO = ("gemma-4-26b-a4b-it", "gemini-2.5-flash-lite")

CODIGOS_HTTP_TRANSITORIOS = {408, 429, 500, 502, 503, 504}
MARCADORES_ERRO_TRANSITORIO = (
    "503",
    "429",
    "unavailable",
    "high demand",
    "resource_exhausted",
    "overloaded",
    "rate limit",
    "quota",
    "temporarily",
    "try again later",
    "timed out",
    "timeout",
)


@dataclass
class AnalisadorVisualGoogleAIStudio:
    """Adaptador outbound de análise visual usando o SDK oficial google-genai (Gemma 4 31B)."""

    chave: str = ""
    modelo: str = MODELO_PADRAO_GEMMA_VISUAL
    prompt: str = PROMPT_ANALISE_VISUAL_PADRAO
    temperatura: float = 0.0
    timeout_segundos: float = 60.0
    provedor: str = "google_ai_studio"
    fonte_unidade: str = "google_ai_studio"
    modelos_fallback: tuple[str, ...] = MODELOS_FALLBACK_PADRAO
    max_tentativas: int = 3
    backoff_inicial_segundos: float = 2.0
    intervalo_entre_requisicoes_segundos: float = 0.5
    max_concorrencia: int = 2
    cliente: Any = None
    genai_sdk: Any = None
    sleep_fn: Callable[[float], None] = time.sleep
    clock_fn: Callable[[], float] = time.monotonic
    _ultimo_envio: float | None = field(default=None, init=False, repr=False, compare=False)
    _lock_pacing: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False, compare=False
    )
    _semaforo: threading.Semaphore = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._semaforo = threading.Semaphore(max(1, int(self.max_concorrencia)))

    def validar_modelo_visual(self) -> None:
        if self.cliente is None and not self.chave.strip():
            raise ErroAnaliseVisual(
                "Chave do Google AI Studio não configurada: defina "
                "ANOTAI_GOOGLE_API_KEY (ou GEMINI_API_KEY)."
            )

    def _obter_modulos_sdk(self) -> tuple[Any, Any]:
        if self.genai_sdk is not None:
            return self.genai_sdk, getattr(self.genai_sdk, "types", None)
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ErroAnaliseVisual(
                "SDK do Google GenAI não instalado. Execute: uv sync --extra google"
            ) from exc
        return genai, types

    def _obter_cliente(self) -> tuple[Any, Any]:
        if self.cliente is not None:
            types_mod = getattr(self.genai_sdk, "types", None)
            if types_mod is None:
                try:
                    from google.genai import types as types_mod
                except ImportError:
                    types_mod = None
            return self.cliente, types_mod

        genai, types = self._obter_modulos_sdk()
        http_options = self._construir_http_options(types)
        kwargs: dict[str, Any] = {"api_key": self.chave.strip()}
        if http_options is not None:
            kwargs["http_options"] = http_options
        self.cliente = genai.Client(**kwargs)
        return self.cliente, types

    def _construir_http_options(self, types: Any) -> Any:
        if types is None or not hasattr(types, "HttpOptions"):
            return None
        return types.HttpOptions(timeout=max(1000, int(self.timeout_segundos * 1000)))

    def analisar(self, imagem: bytes, numero_pagina: int) -> list[dict[str, Any]]:
        if not imagem:
            raise ErroAnaliseVisual("imagem da página vazia")
        self.validar_modelo_visual()

        cliente, types = self._obter_cliente()
        mime_type = "image/jpeg" if imagem.startswith(b"\xff\xd8\xff") else "image/png"

        if types is not None and hasattr(types, "Part") and hasattr(types.Part, "from_bytes"):
            parte_imagem = types.Part.from_bytes(data=imagem, mime_type=mime_type)
        else:
            parte_imagem = {"mime_type": mime_type, "data": imagem}

        if types is not None and hasattr(types, "GenerateContentConfig"):
            config: Any = types.GenerateContentConfig(temperature=self.temperatura)
        else:
            config = {"temperature": self.temperatura}

        resposta, modelo_usado = self._executar_com_retry_e_fallback(
            cliente=cliente,
            contents=[parte_imagem, self.prompt],
            config=config,
            numero_pagina=numero_pagina,
        )
        if resposta is None:
            return []

        conteudo = self._extrair_texto_resposta(resposta)
        try:
            dados = AnalisadorVisualOllama._interpretar_resposta(conteudo)
        except ErroAnaliseVisual as exc:
            logger.warning(
                "Resposta inválida do Google AI Studio (%s) no elemento da página %s; "
                "continuando sem unidades OCR: %s",
                modelo_usado,
                numero_pagina,
                self._sanitizar_mensagem(str(exc)),
            )
            return []

        unidades = AnalisadorVisualOllama.normalizar_dados_visuais(
            dados,
            numero_pagina,
            provedor_nome="Google AI Studio",
        )
        if modelo_usado != (self.modelo.strip() or MODELO_PADRAO_GEMMA_VISUAL):
            for unidade in unidades:
                unidade["model"] = modelo_usado
        return unidades

    def _modelos_candidatos(self) -> list[str]:
        primario = self.modelo.strip() or MODELO_PADRAO_GEMMA_VISUAL
        candidatos: list[str] = [primario]
        for fallback in self.modelos_fallback:
            limpo = fallback.strip()
            if limpo and limpo not in candidatos:
                candidatos.append(limpo)
        return candidatos

    def _aguardar_pacing(self) -> None:
        intervalo = max(0.0, float(self.intervalo_entre_requisicoes_segundos))
        if intervalo <= 0.0:
            return
        with self._lock_pacing:
            agora = float(self.clock_fn())
            if self._ultimo_envio is not None:
                decorrido = agora - self._ultimo_envio
                restante = intervalo - decorrido
                if restante > 0.0:
                    self.sleep_fn(restante)
            self._ultimo_envio = float(self.clock_fn())

    def _executar_com_retry_e_fallback(
        self,
        *,
        cliente: Any,
        contents: list[Any],
        config: Any,
        numero_pagina: int,
    ) -> tuple[Any, str]:
        modelos = self._modelos_candidatos()
        modelo_primario = modelos[0]
        tentativas_por_modelo = max(1, int(self.max_tentativas))

        for idx_modelo, modelo_atual in enumerate(modelos):
            tem_proximo_modelo = idx_modelo < len(modelos) - 1
            for tentativa in range(tentativas_por_modelo):
                try:
                    with self._semaforo:
                        self._aguardar_pacing()
                        resposta = cliente.models.generate_content(
                            model=modelo_atual,
                            contents=contents,
                            config=config,
                        )
                    if modelo_atual != modelo_primario:
                        logger.info(
                            "Google AI Studio atendeu a página %s usando modelo fallback '%s'.",
                            numero_pagina,
                            modelo_atual,
                        )
                    return resposta, modelo_atual
                except ErroAnaliseVisual:
                    raise
                except Exception as exc:
                    categoria, status = self._classificar_erro(exc)
                    resumo = self._sanitizar_mensagem(str(exc).strip() or exc.__class__.__name__)
                    if categoria == "auth":
                        rotulo_status = status if isinstance(status, int) else "401/403"
                        raise ErroAnaliseVisual(
                            "Falha de autenticação/autorização no Google AI Studio "
                            f"(HTTP {rotulo_status})"
                        ) from exc

                    if categoria == "not_found":
                        logger.warning(
                            "Modelo '%s' indisponível/não encontrado no Google AI Studio "
                            "(página %s)%s: %s",
                            modelo_atual,
                            numero_pagina,
                            "; tentando próximo fallback" if tem_proximo_modelo else "",
                            resumo,
                        )
                        break

                    if categoria == "transient" and tentativa < tentativas_por_modelo - 1:
                        atraso = self._calcular_backoff(tentativa)
                        logger.warning(
                            "Erro transitório no Google AI Studio (%s) na página %s "
                            "(tentativa %s/%s); aguardando %.1fs para tentar novamente: %s",
                            modelo_atual,
                            numero_pagina,
                            tentativa + 1,
                            tentativas_por_modelo,
                            atraso,
                            resumo,
                        )
                        if atraso > 0.0:
                            self.sleep_fn(atraso)
                        continue

                    if tem_proximo_modelo:
                        logger.warning(
                            "Falha ao consultar Google AI Studio (%s) na página %s após %s "
                            "tentativa(s); tentando modelo fallback '%s': %s",
                            modelo_atual,
                            numero_pagina,
                            tentativa + 1,
                            modelos[idx_modelo + 1],
                            resumo,
                        )
                        break

                    logger.warning(
                        "Falha ao consultar Google AI Studio (%s) na página %s; "
                        "continuando sem unidades OCR: %s",
                        modelo_atual,
                        numero_pagina,
                        resumo,
                    )
                    return None, modelo_atual

        return None, modelo_primario

    def _calcular_backoff(self, tentativa: int) -> float:
        base = max(0.0, float(self.backoff_inicial_segundos))
        if base <= 0.0:
            return 0.0
        jitter = random.uniform(0.0, min(0.5, base * 0.25))
        return round(base * (2**tentativa) + jitter, 3)

    @classmethod
    def _classificar_erro(cls, exc: Exception) -> tuple[str, int | None]:
        status = getattr(exc, "code", None)
        if status is None:
            status = getattr(exc, "status_code", None)
        mensagem = str(getattr(exc, "message", "") or exc)
        detalhes = str(getattr(exc, "details", "") or "")
        status_str = str(getattr(exc, "status", "") or "")
        texto = f"{mensagem} {detalhes} {status_str}".lower()

        if status in (401, 403) or "api_key_invalid" in texto or "api key not valid" in texto:
            return "auth", status if isinstance(status, int) else None

        if status == 404 or "not_found" in texto:
            return "not_found", 404

        if isinstance(exc, (TimeoutError, OSError)) or status in CODIGOS_HTTP_TRANSITORIOS:
            return "transient", status if isinstance(status, int) else None

        if any(marcador in texto for marcador in MARCADORES_ERRO_TRANSITORIO):
            return "transient", status if isinstance(status, int) else None

        return "fatal", status if isinstance(status, int) else None

    def _sanitizar_mensagem(self, mensagem: str) -> str:
        chave = self.chave.strip()
        if chave and chave in mensagem:
            return mensagem.replace(chave, "***")
        return mensagem

    @staticmethod
    def _extrair_texto_resposta(resposta: Any) -> str:
        if resposta is None:
            return ""
        candidatos = (
            resposta.get("candidates")
            if isinstance(resposta, dict)
            else getattr(resposta, "candidates", None)
        )
        if isinstance(candidatos, list) and candidatos:
            primeiro = candidatos[0]
            conteudo = (
                primeiro.get("content")
                if isinstance(primeiro, dict)
                else getattr(primeiro, "content", None)
            )
            partes = (
                conteudo.get("parts")
                if isinstance(conteudo, dict)
                else getattr(conteudo, "parts", None)
            )
            if isinstance(partes, list):
                textos_finais: list[str] = []
                todos_textos: list[str] = []
                for parte in partes:
                    texto = (
                        parte.get("text")
                        if isinstance(parte, dict)
                        else getattr(parte, "text", None)
                    )
                    if not isinstance(texto, str) or not texto.strip():
                        continue
                    todos_textos.append(texto)
                    eh_pensamento = (
                        parte.get("thought")
                        if isinstance(parte, dict)
                        else getattr(parte, "thought", False)
                    )
                    if not eh_pensamento:
                        textos_finais.append(texto)
                escolhidos = textos_finais or todos_textos
                if escolhidos:
                    return "\n".join(escolhidos).strip()

        texto_direto = (
            resposta.get("text") if isinstance(resposta, dict) else getattr(resposta, "text", None)
        )
        return str(texto_direto).strip() if isinstance(texto_direto, str) else ""
