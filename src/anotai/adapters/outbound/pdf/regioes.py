from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pymupdf as fitz

from anotai.domain.value_objects import CaixaDelimitadora

from .normalizacao import normalizar_conteudo_extraido

MIN_LINHAS_TABELA = 2
MIN_COLUNAS_TABELA = 2
MIN_PREENCHIMENTO_TABELA = 0.50
PROPORCAO_AREA_MIN_TABELA = 0.02

MIN_PRIMITIVOS_REGIAO_VETORIAL = 8
PROPORCAO_AREA_MIN_VETORIAL = 0.04
PROPORCAO_AREA_MAX_VETORIAL = 0.85
LIMIAR_SOBREPOSICAO_REGIAO = 0.50
MAX_REGIOES_VETORIAIS_POR_PAGINA = 3
DPI_RECORTE_VETORIAL = 150


@dataclass(frozen=True, slots=True)
class RegiaoTabela:
    ordem: int
    caixa: CaixaDelimitadora
    texto: str
    evidencia: str


@dataclass(frozen=True, slots=True)
class RegiaoVetorial:
    ordem: int
    caixa: CaixaDelimitadora
    conteudo_bytes: bytes
    evidencia: str
    proporcao_area: float


def _area_caixa(c: CaixaDelimitadora) -> float:
    return max(0.0, (c.x1 - c.x0) * (c.y1 - c.y0))


def _proporcao_sobreposicao(a: CaixaDelimitadora, b: CaixaDelimitadora) -> float:
    ix0 = max(a.x0, b.x0)
    iy0 = max(a.y0, b.y0)
    ix1 = min(a.x1, b.x1)
    iy1 = min(a.y1, b.y1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    area_inter = (ix1 - ix0) * (iy1 - iy0)
    area_menor = min(_area_caixa(a), _area_caixa(b))
    return area_inter / area_menor if area_menor > 0.0 else 0.0


def ponto_em_caixas(
    cx: float,
    cy: float,
    caixas: Sequence[CaixaDelimitadora],
) -> bool:
    return any(c.x0 <= cx <= c.x1 and c.y0 <= cy <= c.y1 for c in caixas)


def detectar_tabelas(
    pagina: fitz.Page,
    linhas_template: set[str],
) -> list[RegiaoTabela]:
    """Detecta tabelas nativas via PyMuPDF find_tables filtrando falsos positivos."""
    ret_pag = pagina.rect
    area_pagina = max(1.0, float(ret_pag.width * ret_pag.height))

    try:
        finder = pagina.find_tables()
        tabelas_raw = getattr(finder, "tables", []) or []
    except Exception:
        return []

    resultado: list[RegiaoTabela] = []
    for tab in tabelas_raw:
        bbox = getattr(tab, "bbox", None)
        if not bbox or len(bbox) < 4:
            continue
        caixa = CaixaDelimitadora(
            round(float(bbox[0]), 2),
            round(float(bbox[1]), 2),
            round(float(bbox[2]), 2),
            round(float(bbox[3]), 2),
        )
        if _area_caixa(caixa) / area_pagina < PROPORCAO_AREA_MIN_TABELA:
            continue

        try:
            linhas_raw = tab.extract() or []
        except Exception:
            continue

        if len(linhas_raw) < MIN_LINHAS_TABELA:
            continue
        max_cols = max((len(r) for r in linhas_raw), default=0)
        if max_cols < MIN_COLUNAS_TABELA:
            continue

        total_celulas = 0
        celulas_preenchidas = 0
        linhas_formatadas: list[str] = []
        for row in linhas_raw:
            celulas_linha: list[str] = []
            for cel in row:
                total_celulas += 1
                txt = normalizar_conteudo_extraido(str(cel)) if cel is not None else ""
                if txt and txt not in linhas_template:
                    celulas_preenchidas += 1
                    celulas_linha.append(txt)
                else:
                    celulas_linha.append("")
            if any(celulas_linha):
                linhas_formatadas.append(" | ".join(c for c in celulas_linha if c))

        if total_celulas == 0 or (celulas_preenchidas / total_celulas) < MIN_PREENCHIMENTO_TABELA:
            continue
        texto_tabela = "\n".join(linhas_formatadas).strip()
        if not texto_tabela:
            continue

        ordem = len(resultado) + 1
        resultado.append(
            RegiaoTabela(
                ordem=ordem,
                caixa=caixa,
                texto=texto_tabela,
                evidencia=f"table-native-{pagina.number + 1}-{ordem}",
            )
        )

    return resultado


def detectar_regioes_vetoriais(
    pagina: fitz.Page,
    *,
    piso_drawings: int,
    caixas_tabelas: Sequence[CaixaDelimitadora],
    caixas_imagens: Sequence[CaixaDelimitadora],
) -> list[RegiaoVetorial]:
    """Detecta clusters de desenhos vetoriais (gráficos/diagramas) e gera recorte PNG."""
    try:
        drawings = pagina.get_drawings() or []
    except Exception:
        return []

    if len(drawings) - piso_drawings < MIN_PRIMITIVOS_REGIAO_VETORIAL:
        return []

    try:
        clusters = pagina.cluster_drawings() or []
    except Exception:
        return []

    ret_pag = pagina.rect
    area_pagina = max(1.0, float(ret_pag.width * ret_pag.height))
    caixas_bloqueio = [*caixas_tabelas, *caixas_imagens]

    candidatas: list[tuple[CaixaDelimitadora, float, fitz.Rect]] = []
    for rect_raw in clusters:
        rect = fitz.Rect(rect_raw) & ret_pag
        if rect.is_empty or rect.width <= 1.0 or rect.height <= 1.0:
            continue
        caixa = CaixaDelimitadora(
            round(float(rect.x0), 2),
            round(float(rect.y0), 2),
            round(float(rect.x1), 2),
            round(float(rect.y1), 2),
        )
        prop = _area_caixa(caixa) / area_pagina
        if prop < PROPORCAO_AREA_MIN_VETORIAL or prop > PROPORCAO_AREA_MAX_VETORIAL:
            continue

        if any(
            _proporcao_sobreposicao(caixa, b) > LIMIAR_SOBREPOSICAO_REGIAO
            for b in caixas_bloqueio
        ):
            continue

        # Conta quantos primitivos de desenho estão contidos no cluster
        n_primitivos = 0
        for d in drawings:
            d_rect = d.get("rect")
            if d_rect is None:
                continue
            dr = fitz.Rect(d_rect)
            if rect.intersects(dr):
                n_primitivos += 1
        if n_primitivos < MIN_PRIMITIVOS_REGIAO_VETORIAL:
            continue

        candidatas.append((caixa, prop, rect))

    candidatas.sort(key=lambda item: item[1], reverse=True)
    selecionadas = candidatas[:MAX_REGIOES_VETORIAIS_POR_PAGINA]

    regioes: list[RegiaoVetorial] = []
    for idx, (caixa, prop, rect) in enumerate(selecionadas, start=1):
        try:
            pix = pagina.get_pixmap(dpi=DPI_RECORTE_VETORIAL, clip=rect, alpha=False)
            png_bytes = pix.tobytes("png")
        except Exception:
            continue
        regioes.append(
            RegiaoVetorial(
                ordem=idx,
                caixa=caixa,
                conteudo_bytes=png_bytes,
                evidencia=f"vector-region-{pagina.number + 1}-{idx}",
                proporcao_area=round(prop, 4),
            )
        )

    return regioes


__all__ = [
    "RegiaoTabela",
    "RegiaoVetorial",
    "detectar_regioes_vetoriais",
    "detectar_tabelas",
    "ponto_em_caixas",
]
