from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import pymupdf as fitz

from anotai.domain.value_objects import CaixaDelimitadora

DIMENSAO_MINIMA_IMAGEM_PX = 64
PROPORCAO_AREA_MINIMA_IMAGEM = 0.02
PROPORCAO_IMAGEM_PAGINA_INTEIRA = 0.85
MINIMO_PAGINAS_FILTRO_TEMPLATE = 4
PROPORCAO_PAGINAS_TEMPLATE = 0.50
MAXIMO_IMAGENS_POR_PAGINA = 4
LIMIAR_CARACTERES_UTEIS_SLIDE_VISUAL = 80
EXCEDENTE_MINIMO_DRAWINGS_VETORIAIS = 15
DPI_RENDERIZACAO_PAGINA = 150


@dataclass(frozen=True, slots=True)
class ImagemBrutaPdf:
    ordem: int
    xref: int
    conteudo_bytes: bytes
    formato: str
    largura: int
    altura: int
    caixa: CaixaDelimitadora
    proporcao_area: float

    @property
    def evidencia(self) -> str:
        return f"image-xref-{self.xref}"


@dataclass(frozen=True, slots=True)
class RenderPaginaPdf:
    conteudo_bytes: bytes
    caixa: CaixaDelimitadora
    evidencia: str


def identificar_linhas_repetidas_template(textos_paginas: Sequence[str]) -> set[str]:
    total_paginas = len(textos_paginas)
    if total_paginas < MINIMO_PAGINAS_FILTRO_TEMPLATE:
        return set()

    contagem_por_linha: Counter[str] = Counter()
    for texto in textos_paginas:
        linhas_unicas = {
            linha.strip()
            for linha in (texto or "").splitlines()
            if linha.strip() and not linha.strip().isdigit()
        }
        for linha in linhas_unicas:
            contagem_por_linha[linha] += 1

    return {
        linha
        for linha, freq in contagem_por_linha.items()
        if freq >= MINIMO_PAGINAS_FILTRO_TEMPLATE
        and (freq / total_paginas) > PROPORCAO_PAGINAS_TEMPLATE
    }


def contar_caracteres_uteis(texto_pagina: str, linhas_template: set[str]) -> int:
    linhas_uteis = [
        limpa
        for linha in (texto_pagina or "").splitlines()
        if (limpa := linha.strip()) and not limpa.isdigit() and limpa not in linhas_template
    ]
    return len(" ".join(linhas_uteis).strip())


def identificar_xrefs_template(doc: fitz.Document) -> set[int]:
    total_paginas = doc.page_count
    if total_paginas < MINIMO_PAGINAS_FILTRO_TEMPLATE:
        return set()

    contagem_xref: Counter[int] = Counter()
    for idx_pag in range(total_paginas):
        pagina = doc.load_page(idx_pag)
        xrefs_pagina: set[int] = set()
        for info in pagina.get_images(full=True):
            xref = int(info[0])
            largura = int(info[2]) if len(info) > 2 else 0
            altura = int(info[3]) if len(info) > 3 else 0
            if largura >= DIMENSAO_MINIMA_IMAGEM_PX and altura >= DIMENSAO_MINIMA_IMAGEM_PX:
                xrefs_pagina.add(xref)
        for xref in xrefs_pagina:
            contagem_xref[xref] += 1

    return {
        xref
        for xref, freq in contagem_xref.items()
        if freq >= MINIMO_PAGINAS_FILTRO_TEMPLATE
        and (freq / total_paginas) > PROPORCAO_PAGINAS_TEMPLATE
    }


def calcular_piso_drawings(doc: fitz.Document) -> int:
    if doc.page_count < 2:
        return 0
    amostra = min(doc.page_count, 10)
    contagens: list[int] = []
    for idx in range(amostra):
        pagina = doc.load_page(idx)
        try:
            contagens.append(len(pagina.get_drawings()))
        except Exception:
            contagens.append(0)
    return min(contagens) if contagens else 0


def converter_xref_para_png_rgb(
    doc: fitz.Document,
    xref: int,
    smask: int = 0,
) -> tuple[bytes, int, int] | None:
    try:
        pix_base = fitz.Pixmap(doc, xref)
    except Exception:
        return None

    try:
        if smask > 0:
            try:
                pix_mask = fitz.Pixmap(doc, smask)
                if (
                    pix_base.alpha == 0
                    and pix_base.width == pix_mask.width
                    and pix_base.height == pix_mask.height
                ):
                    pix_base = fitz.Pixmap(pix_base, pix_mask)
            except Exception:
                pass

        precisa_converter_rgb = (
            pix_base.colorspace is None or pix_base.colorspace.n != 3 or pix_base.alpha != 0
        )
        pix_rgb = fitz.Pixmap(fitz.csRGB, pix_base) if precisa_converter_rgb else pix_base
        largura = int(pix_rgb.width)
        altura = int(pix_rgb.height)
        if largura < DIMENSAO_MINIMA_IMAGEM_PX or altura < DIMENSAO_MINIMA_IMAGEM_PX:
            return None
        return pix_rgb.tobytes("png"), largura, altura
    except Exception:
        return None


def _calcular_caixa_e_proporcao(
    pagina: fitz.Page,
    xref: int,
    largura_px: int,
    altura_px: int,
) -> tuple[CaixaDelimitadora, float]:
    ret_pag = pagina.rect
    area_pagina = max(1.0, float(ret_pag.width * ret_pag.height))
    try:
        retangulos = pagina.get_image_rects(xref)
    except Exception:
        retangulos = []

    if retangulos:
        melhor_ret = max(
            retangulos,
            key=lambda r: max(0.0, float((r & ret_pag).width * (r & ret_pag).height)),
        )
        intersecao = melhor_ret & ret_pag
        area_img = max(0.0, float(intersecao.width * intersecao.height))
        proporcao = min(1.0, area_img / area_pagina)
        caixa = CaixaDelimitadora(
            round(float(melhor_ret.x0), 2),
            round(float(melhor_ret.y0), 2),
            round(float(melhor_ret.x1), 2),
            round(float(melhor_ret.y1), 2),
        )
        return caixa, round(proporcao, 4)

    proporcao_estimada = min(1.0, float(largura_px * altura_px) / max(1.0, area_pagina * 4.0))
    caixa_padrao = CaixaDelimitadora(
        0.0,
        0.0,
        round(float(ret_pag.width), 2),
        round(float(ret_pag.height), 2),
    )
    return caixa_padrao, round(max(PROPORCAO_AREA_MINIMA_IMAGEM, proporcao_estimada), 4)


def renderizar_pagina_png(pagina: fitz.Page) -> bytes | None:
    try:
        pix = pagina.get_pixmap(dpi=DPI_RENDERIZACAO_PAGINA, alpha=False)
        return pix.tobytes("png")
    except Exception:
        return None


def extrair_insumos_visuais_pagina(
    doc: fitz.Document,
    pagina: fitz.Page,
    *,
    texto_nativo: str,
    caracteres_uteis: int,
    xrefs_template: set[int],
    piso_drawings: int,
    tem_regioes_vetoriais: bool = False,
) -> tuple[list[ImagemBrutaPdf], RenderPaginaPdf | None]:
    candidatas_raw: list[tuple[int, int, int, int, CaixaDelimitadora, float]] = []
    xrefs_vistos: set[int] = set()

    for info in pagina.get_images(full=True):
        xref = int(info[0])
        smask = int(info[1]) if len(info) > 1 else 0
        largura = int(info[2]) if len(info) > 2 else 0
        altura = int(info[3]) if len(info) > 3 else 0
        if xref in xrefs_vistos or xref in xrefs_template:
            continue
        xrefs_vistos.add(xref)

        if largura < DIMENSAO_MINIMA_IMAGEM_PX or altura < DIMENSAO_MINIMA_IMAGEM_PX:
            continue

        caixa, proporcao = _calcular_caixa_e_proporcao(pagina, xref, largura, altura)
        if proporcao < PROPORCAO_AREA_MINIMA_IMAGEM:
            continue

        candidatas_raw.append((xref, smask, largura, altura, caixa, proporcao))

    ret_pag = pagina.rect
    caixa_pagina = CaixaDelimitadora(
        0.0,
        0.0,
        round(float(ret_pag.width), 2),
        round(float(ret_pag.height), 2),
    )
    sem_texto_nativo = not texto_nativo.strip()

    # Caso 1: Página digitalizada/escaneada coberta por uma única imagem de página inteira
    if (
        sem_texto_nativo
        and len(candidatas_raw) == 1
        and candidatas_raw[0][5] >= PROPORCAO_IMAGEM_PAGINA_INTEIRA
    ):
        png_bytes = renderizar_pagina_png(pagina)
        if png_bytes is not None:
            return [], RenderPaginaPdf(
                conteudo_bytes=png_bytes,
                caixa=candidatas_raw[0][4],
                evidencia=f"image-xref-{candidatas_raw[0][0]}",
            )
        return [], None

    # Caso 2: Página com excesso de recortes fragmentados (> MAXIMO_IMAGENS_POR_PAGINA)
    if len(candidatas_raw) > MAXIMO_IMAGENS_POR_PAGINA:
        png_bytes = renderizar_pagina_png(pagina)
        if png_bytes is not None:
            return [], RenderPaginaPdf(
                conteudo_bytes=png_bytes,
                caixa=caixa_pagina,
                evidencia=f"page-render-{pagina.number + 1}",
            )
        return [], None

    imagens_extraidas: list[ImagemBrutaPdf] = []
    for xref, smask, _, _, caixa, proporcao in candidatas_raw:
        convertida = converter_xref_para_png_rgb(doc, xref, smask=smask)
        if convertida is None:
            continue
        png_bytes, larg_real, alt_real = convertida
        imagens_extraidas.append(
            ImagemBrutaPdf(
                ordem=len(imagens_extraidas) + 1,
                xref=xref,
                conteudo_bytes=png_bytes,
                formato="png",
                largura=larg_real,
                altura=alt_real,
                caixa=caixa,
                proporcao_area=proporcao,
            )
        )

    render_pagina: RenderPaginaPdf | None = None
    if (
        caracteres_uteis < LIMIAR_CARACTERES_UTEIS_SLIDE_VISUAL
        and not imagens_extraidas
        and not tem_regioes_vetoriais
    ):
        try:
            total_drawings = len(pagina.get_drawings())
        except Exception:
            total_drawings = 0
        excedente_drawings = max(0, total_drawings - piso_drawings)

        if excedente_drawings >= EXCEDENTE_MINIMO_DRAWINGS_VETORIAIS:
            png_bytes = renderizar_pagina_png(pagina)
            if png_bytes is not None:
                render_pagina = RenderPaginaPdf(
                    conteudo_bytes=png_bytes,
                    caixa=caixa_pagina,
                    evidencia=f"page-render-{pagina.number + 1}",
                )

    return imagens_extraidas, render_pagina


__all__ = [
    "DIMENSAO_MINIMA_IMAGEM_PX",
    "DPI_RENDERIZACAO_PAGINA",
    "EXCEDENTE_MINIMO_DRAWINGS_VETORIAIS",
    "ImagemBrutaPdf",
    "LIMIAR_CARACTERES_UTEIS_SLIDE_VISUAL",
    "MAXIMO_IMAGENS_POR_PAGINA",
    "MINIMO_PAGINAS_FILTRO_TEMPLATE",
    "PROPORCAO_AREA_MINIMA_IMAGEM",
    "PROPORCAO_IMAGEM_PAGINA_INTEIRA",
    "PROPORCAO_PAGINAS_TEMPLATE",
    "RenderPaginaPdf",
    "calcular_piso_drawings",
    "contar_caracteres_uteis",
    "converter_xref_para_png_rgb",
    "extrair_insumos_visuais_pagina",
    "identificar_linhas_repetidas_template",
    "identificar_xrefs_template",
    "renderizar_pagina_png",
]
