from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pymupdf

from anotai.application.ports import AnalisadorVisual
from anotai.domain.entities import Documento, PaginaDocumento, UnidadeDocumento
from anotai.domain.exceptions import DocumentoInvalido, MetodoExtracaoNaoSuportado
from anotai.domain.value_objects import CaixaDelimitadora, ProvenienciaDocumento

from .imagens import (
    DIMENSAO_MINIMA_IMAGEM_PX,
    DPI_RENDERIZACAO_PAGINA,
    EXCEDENTE_MINIMO_DRAWINGS_VETORIAIS,
    LIMIAR_CARACTERES_UTEIS_SLIDE_VISUAL,
    MAXIMO_IMAGENS_POR_PAGINA,
    MINIMO_PAGINAS_FILTRO_TEMPLATE,
    PROPORCAO_AREA_MINIMA_IMAGEM,
    PROPORCAO_IMAGEM_PAGINA_INTEIRA,
    PROPORCAO_PAGINAS_TEMPLATE,
    ImagemBrutaPdf,
    RenderPaginaPdf,
    calcular_piso_drawings,
    contar_caracteres_uteis,
    converter_xref_para_png_rgb,
    extrair_insumos_visuais_pagina,
    identificar_linhas_repetidas_template,
    identificar_xrefs_template,
    renderizar_pagina_png,
)
from .layout import detectar_colunas, ordenar_por_leitura
from .normalizacao import (
    limpar_texto_pagina,
    normalizar_conteudo_extraido,
)
from .regioes import RegiaoVetorial, detectar_regioes_vetoriais, detectar_tabelas
from .unidades import segmentar_unidades_pagina

PIPELINE_VERSION = "v1"
METODOS = {"native", "native_then_ocr"}
LIMITE_MAXIMO_BYTES_PDF = 100 * 1024 * 1024  # 100 MB
LIMITE_MAXIMO_PAGINAS_PDF = 2000


@dataclass(slots=True)
class _PaginaExtraidaBruta:
    numero_pagina: int
    pagina_id: str
    texto_nativo: str
    texto_limpo: str
    unidades_nativas: list[UnidadeDocumento]
    elementos_visuais: list[tuple[str, bytes, CaixaDelimitadora | None]]
    eh_render_pagina_inteira: bool
    colunas: list[tuple[float, float]]


class ExtratorPDF:
    _normalizar = staticmethod(normalizar_conteudo_extraido)

    def __init__(
        self,
        analisador_visual: AnalisadorVisual | None = None,
    ) -> None:
        self._analisador_visual = analisador_visual

    @staticmethod
    def _abrir_documento_validado(caminho: Path) -> pymupdf.Document:
        if not caminho.is_file() or caminho.suffix.lower() != ".pdf":
            raise DocumentoInvalido(f"arquivo PDF inválido: {caminho}")
        try:
            conteudo_pdf = caminho.read_bytes()
        except OSError as exc:
            raise DocumentoInvalido(f"não foi possível ler: {caminho}") from exc

        if not conteudo_pdf:
            raise DocumentoInvalido("O arquivo PDF está vazio")
        if len(conteudo_pdf) > LIMITE_MAXIMO_BYTES_PDF:
            raise DocumentoInvalido("O arquivo PDF excede o limite máximo de 100 MB")

        try:
            doc = pymupdf.open(stream=conteudo_pdf, filetype="pdf")
        except Exception as exc:
            raise DocumentoInvalido(f"não foi possível abrir: {caminho}") from exc

        if doc.needs_pass or doc.is_encrypted:
            doc.close()
            raise DocumentoInvalido(
                "O arquivo PDF está protegido por senha. Envie uma versão desbloqueada"
            )

        total_paginas = doc.page_count
        if doc.is_closed or total_paginas < 1 or total_paginas > LIMITE_MAXIMO_PAGINAS_PDF:
            doc.close()
            raise DocumentoInvalido("PDF sem páginas ou fora do limite permitido")

        return doc

    @staticmethod
    def _inferir_tipo_material(doc: pymupdf.Document) -> str:
        total = doc.page_count
        paginas_paisagem = 0
        soma_palavras = 0
        amostra = min(total, 10)
        for idx in range(amostra):
            pagina = doc.load_page(idx)
            ret = pagina.rect
            if ret.width > ret.height:
                paginas_paisagem += 1
            texto = pagina.get_text("text") or ""
            soma_palavras += len(texto.split())

        media_palavras = (soma_palavras / amostra) if amostra > 0 else 0.0
        if paginas_paisagem >= (amostra / 2) and media_palavras < 120:
            return "slides"
        return "apostila"

    def extrair(self, caminho: Path, metodo: str = "native_then_ocr") -> Documento:
        if metodo not in METODOS:
            raise MetodoExtracaoNaoSuportado(metodo)

        pdf = self._abrir_documento_validado(caminho)
        try:
            documento_id = f"doc-{hashlib.sha256(str(caminho.resolve()).encode()).hexdigest()[:16]}"
            tipo_material = self._inferir_tipo_material(pdf)
            paginas_brutas, total_tabelas, total_regioes = self._extrair_estrutura_bruta(
                pdf, documento_id
            )
        finally:
            pdf.close()

        paginas = self._processar_ocr_e_montar_paginas(
            paginas_brutas=paginas_brutas,
            documento_id=documento_id,
            metodo=metodo,
        )

        return Documento(
            id_documento=documento_id,
            uri_origem=str(caminho),
            titulo=caminho.stem,
            paginas=paginas,
            versao_processamento=PIPELINE_VERSION,
            proveniencia=ProvenienciaDocumento(
                uri_origem=str(caminho),
                metodo_extracao=metodo,
                versao_pipeline=PIPELINE_VERSION,
                modelo=getattr(self._analisador_visual, "modelo", None),
                configuracao={
                    "ocr_escopo": "elementos_visuais",
                    "tipo_material": tipo_material,
                    "tabelas_nativas": total_tabelas,
                    "regioes_vetoriais": total_regioes,
                    **(
                        {"provedor_visual": provedor_visual}
                        if (
                            provedor_visual := getattr(
                                self._analisador_visual, "provedor", None
                            )
                        )
                        else {}
                    ),
                },
                prompt=getattr(self._analisador_visual, "prompt", None),
                executado_em=datetime.now(UTC).isoformat(),
            ),
        )

    def _extrair_estrutura_bruta(
        self,
        pdf: pymupdf.Document,
        documento_id: str,
    ) -> list[_PaginaExtraidaBruta]:
        total_paginas = pdf.page_count
        textos_nativos = [
            pdf.load_page(indice).get_text("text") or "" for indice in range(total_paginas)
        ]
        linhas_template = identificar_linhas_repetidas_template(textos_nativos)
        xrefs_template = identificar_xrefs_template(pdf)
        piso_drawings = calcular_piso_drawings(pdf)

        paginas_brutas: list[_PaginaExtraidaBruta] = []
        total_tabelas_nativas = 0
        total_regioes_vetoriais = 0
        for indice in range(total_paginas):
            pagina = pdf.load_page(indice)
            texto_nativo = textos_nativos[indice]
            pagina_id = f"{documento_id}-page-{indice + 1}"
            caracteres_uteis = contar_caracteres_uteis(texto_nativo, linhas_template)
            tabelas_pag = detectar_tabelas(pagina, linhas_template)
            total_tabelas_nativas += len(tabelas_pag)

            imagens_pag, render_pagina = extrair_insumos_visuais_pagina(
                pdf,
                pagina,
                texto_nativo=texto_nativo,
                caracteres_uteis=caracteres_uteis,
                xrefs_template=xrefs_template,
                piso_drawings=piso_drawings,
                tem_regioes_vetoriais=False,
            )
            regioes_vetoriais_pag: list[RegiaoVetorial] = []
            if render_pagina is None:
                regioes_vetoriais_pag = detectar_regioes_vetoriais(
                    pagina,
                    piso_drawings=piso_drawings,
                    caixas_tabelas=[t.caixa for t in tabelas_pag],
                    caixas_imagens=[img.caixa for img in imagens_pag],
                )
                total_regioes_vetoriais += len(regioes_vetoriais_pag)

            # Extrai caixas de linhas para detectar colunas da página
            caixas_linhas: list[tuple[float, float, float, float]] = []
            dados_dict = pagina.get_text("dict", sort=False) or {}
            for b in dados_dict.get("blocks", []):
                if b.get("type") != 0:
                    continue
                for linha_dict in b.get("lines", []):
                    spans = linha_dict.get("spans", [])
                    txt_l = "".join(s.get("text", "") for s in spans).strip()
                    if not txt_l or txt_l in linhas_template or txt_l.isdigit():
                        continue
                    bb = linha_dict.get("bbox", (0.0, 0.0, 0.0, 0.0))
                    caixas_linhas.append(
                        (float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3]))
                    )
            largura_pagina = float(pagina.rect.width) if pagina.rect else 612.0
            colunas_pag = detectar_colunas(caixas_linhas, largura_pagina)

            unidades_nativas = segmentar_unidades_pagina(
                pagina=pagina,
                documento_id=documento_id,
                pagina_id=pagina_id,
                linhas_template=linhas_template,
                imagens=imagens_pag,
                render_pagina=render_pagina,
                tabelas=tabelas_pag,
                regioes_vetoriais=regioes_vetoriais_pag,
                colunas=colunas_pag,
            )
            elementos_visuais = self._montar_elementos_visuais(
                imagens_pag, render_pagina, regioes_vetoriais_pag
            )
            textos_unidades = [u.texto for u in unidades_nativas if u.texto]
            texto_limpo = (
                normalizar_conteudo_extraido(" ".join(textos_unidades))
                if textos_unidades
                else limpar_texto_pagina(texto_nativo, linhas_template)
            )

            paginas_brutas.append(
                _PaginaExtraidaBruta(
                    numero_pagina=indice + 1,
                    pagina_id=pagina_id,
                    texto_nativo=texto_nativo,
                    texto_limpo=texto_limpo,
                    unidades_nativas=unidades_nativas,
                    elementos_visuais=elementos_visuais,
                    eh_render_pagina_inteira=render_pagina is not None,
                    colunas=colunas_pag,
                )
            )
        return paginas_brutas, total_tabelas_nativas, total_regioes_vetoriais

    @staticmethod
    def _montar_elementos_visuais(
        imagens: list[ImagemBrutaPdf],
        render_pagina: RenderPaginaPdf | None,
        regioes_vetoriais: list[RegiaoVetorial] = (),
    ) -> list[tuple[str, bytes, CaixaDelimitadora | None]]:
        if render_pagina is not None:
            return [(render_pagina.evidencia, render_pagina.conteudo_bytes, render_pagina.caixa)]
        itens: list[tuple[str, bytes, CaixaDelimitadora | None]] = [
            (img.evidencia, img.conteudo_bytes, img.caixa) for img in imagens
        ]
        itens.extend((rv.evidencia, rv.conteudo_bytes, rv.caixa) for rv in regioes_vetoriais)
        return itens

    def _processar_ocr_e_montar_paginas(
        self,
        *,
        paginas_brutas: list[_PaginaExtraidaBruta],
        documento_id: str,
        metodo: str,
    ) -> list[PaginaDocumento]:
        cache_analises: dict[str, list[dict[str, Any]]] = {}

        if metodo == "native_then_ocr":
            paginas_com_visuais = [p for p in paginas_brutas if p.elementos_visuais]
            if paginas_com_visuais:
                if self._analisador_visual is None:
                    primeira_pag = paginas_com_visuais[0].numero_pagina
                    raise DocumentoInvalido(
                        f"OCR visual necessário para elementos da página {primeira_pag}, "
                        "mas nenhum analisador visual está configurado"
                    )
                validar = getattr(self._analisador_visual, "validar_modelo_visual", None)
                if callable(validar):
                    validar()

                for pag_bruta in paginas_com_visuais:
                    for _, imagem, _ in pag_bruta.elementos_visuais:
                        chave_cache = self._chave_cache_imagem(imagem)
                        if chave_cache not in cache_analises:
                            cache_analises[chave_cache] = self._analisador_visual.analisar(
                                imagem, pag_bruta.numero_pagina
                            )

        paginas_finais: list[PaginaDocumento] = []
        for pag_bruta in paginas_brutas:
            unidades = list(pag_bruta.unidades_nativas)
            metodo_extracao = "native"

            if metodo == "native_then_ocr" and pag_bruta.elementos_visuais:
                teve_ocr = False
                for evidencia, imagem, caixa in pag_bruta.elementos_visuais:
                    chave_cache = self._chave_cache_imagem(imagem)
                    unidades_analise = cache_analises.get(chave_cache, [])
                    if unidades_analise:
                        teve_ocr = True
                        unidades = self._mesclar_unidades_ocr(
                            unidades,
                            unidades_analise,
                            documento_id,
                            pag_bruta.pagina_id,
                            caixa,
                            evidencia,
                        )
                if teve_ocr:
                    metodo_extracao = "mixed"

            unidades = self._ordenar_unidades(
                unidades, pag_bruta.pagina_id, colunas=pag_bruta.colunas
            )
            texto_normalizado = pag_bruta.texto_limpo

            if metodo_extracao == "mixed":
                textos_ocr = [
                    unidade.texto
                    for unidade in unidades
                    if unidade.fonte in UnidadeDocumento.FONTES_OCR_VISUAL
                    and not unidade.eh_decorativa
                    and unidade.texto
                ]
                if textos_ocr:
                    if pag_bruta.eh_render_pagina_inteira:
                        partes = (
                            [texto_normalizado, *textos_ocr]
                            if texto_normalizado and texto_normalizado not in textos_ocr
                            else textos_ocr
                        )
                    else:
                        partes = [texto_normalizado, *textos_ocr]
                    texto_normalizado = " ".join(parte for parte in partes if parte)

            paginas_finais.append(
                PaginaDocumento(
                    pag_bruta.pagina_id,
                    pag_bruta.numero_pagina,
                    pag_bruta.texto_nativo,
                    texto_normalizado,
                    metodo_extracao,
                    unidades,
                )
            )

        return paginas_finais

    @staticmethod
    def _chave_cache_imagem(imagem: bytes) -> str:
        return hashlib.sha256(b"anotai-visual-v1\0" + imagem).hexdigest()

    def _mesclar_unidades_ocr(
        self,
        nativas: list[UnidadeDocumento],
        unidades_brutas: list[dict[str, Any]],
        documento_id: str,
        pagina_id: str,
        caixa: CaixaDelimitadora | None = None,
        evidencia: str | None = None,
    ) -> list[UnidadeDocumento]:
        unidades = list(nativas)
        eh_decorativa = any(u.get("image_classification") == "decorativo" for u in unidades_brutas)
        if eh_decorativa:
            for unidade_nativa in unidades:
                if (
                    unidade_nativa.tipo == "figure"
                    and evidencia in unidade_nativa.ids_evidencias
                    and unidade_nativa.caixa == caixa
                ):
                    unidade_nativa.eh_decorativa = True

        novas_unidades: list[UnidadeDocumento] = []
        chaves_existentes = {
            (unidade.tipo, unidade.texto, self._chave_caixa(unidade.caixa)) for unidade in unidades
        }
        ordem = len(unidades)
        fonte_visual = self._resolver_fonte_visual()
        for unidade_bruta in unidades_brutas:
            texto_bruto = unidade_bruta.get("text")
            texto = self._normalizar(str(texto_bruto)) if texto_bruto is not None else ""
            tipo = unidade_bruta.get("type", "block")
            if tipo not in UnidadeDocumento.TIPOS_VISUAIS_VALIDOS:
                raise DocumentoInvalido(f"tipo de unidade visual OCR inválido: {tipo}")
            if not texto:
                continue
            chave = (tipo, texto, self._chave_caixa(caixa))
            if chave in chaves_existentes:
                continue
            chaves_existentes.add(chave)
            ordem += 1
            novas_unidades.append(
                UnidadeDocumento(
                    id_unidade=f"{pagina_id}-unit-{ordem}",
                    id_documento=documento_id,
                    id_pagina=pagina_id,
                    tipo=tipo,
                    texto=texto,
                    ordem_leitura=ordem,
                    caixa=caixa,
                    fonte=fonte_visual,
                    ids_evidencias=[evidencia] if evidencia else [],
                    eh_decorativa=eh_decorativa,
                )
            )
        if novas_unidades:
            rotulos_nativos = [
                unidade.texto
                for unidade in unidades
                if unidade.fonte == "native"
                and unidade.tipo == "figure"
                and unidade.texto
                and evidencia in unidade.ids_evidencias
                and unidade.caixa == caixa
            ]
            if rotulos_nativos:
                sufixo = " ".join(rotulos_nativos)
                for nova in novas_unidades:
                    if nova.texto and sufixo not in nova.texto:
                        nova.texto = f"{nova.texto} ({sufixo})"
            unidades = [
                unidade
                for unidade in unidades
                if not (
                    unidade.fonte == "native"
                    and unidade.tipo == "figure"
                    and evidencia in unidade.ids_evidencias
                    and unidade.caixa == caixa
                )
            ]
            unidades.extend(novas_unidades)
        return unidades

    @staticmethod
    def _ordenar_unidades(
        unidades: list[UnidadeDocumento],
        pagina_id: str,
        colunas: list[tuple[float, float]] | None = None,
    ) -> list[UnidadeDocumento]:
        @dataclass(slots=True)
        class _ItemUnidade:
            unidade: UnidadeDocumento
            x0: float
            y0: float
            x1: float
            y1: float

        com_caixa = [
            _ItemUnidade(
                unidade=u,
                x0=u.caixa.x0,
                y0=u.caixa.y0,
                x1=u.caixa.x1,
                y1=u.caixa.y1,
            )
            for u in unidades
            if u.caixa is not None
        ]
        sem_caixa = sorted(
            [u for u in unidades if u.caixa is None],
            key=lambda u: u.ordem_leitura,
        )
        ordenadas_caixa = [
            item.unidade for item in ordenar_por_leitura(com_caixa, colunas or [])
        ]
        ordenadas = [*ordenadas_caixa, *sem_caixa]
        for indice, unidade in enumerate(ordenadas, start=1):
            unidade.ordem_leitura = indice
            unidade.id_unidade = f"{pagina_id}-unit-{indice}"
        return ordenadas

    @staticmethod
    def _chave_caixa(caixa: CaixaDelimitadora | None) -> tuple[float, ...] | None:
        return (caixa.x0, caixa.y0, caixa.x1, caixa.y1) if caixa is not None else None

    def _resolver_fonte_visual(self) -> str:
        fonte = getattr(self._analisador_visual, "fonte_unidade", "ollama")
        if fonte in UnidadeDocumento.FONTES_OCR_VISUAL:
            return str(fonte)
        return "ollama"


__all__ = [
    "DIMENSAO_MINIMA_IMAGEM_PX",
    "DPI_RENDERIZACAO_PAGINA",
    "EXCEDENTE_MINIMO_DRAWINGS_VETORIAIS",
    "ExtratorPDF",
    "LIMIAR_CARACTERES_UTEIS_SLIDE_VISUAL",
    "LIMITE_MAXIMO_BYTES_PDF",
    "LIMITE_MAXIMO_PAGINAS_PDF",
    "MAXIMO_IMAGENS_POR_PAGINA",
    "METODOS",
    "MINIMO_PAGINAS_FILTRO_TEMPLATE",
    "PIPELINE_VERSION",
    "PROPORCAO_AREA_MINIMA_IMAGEM",
    "PROPORCAO_IMAGEM_PAGINA_INTEIRA",
    "PROPORCAO_PAGINAS_TEMPLATE",
    "calcular_piso_drawings",
    "contar_caracteres_uteis",
    "converter_xref_para_png_rgb",
    "identificar_linhas_repetidas_template",
    "identificar_xrefs_template",
    "renderizar_pagina_png",
]
