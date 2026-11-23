from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class ItemEspacial(Protocol):
    @property
    def x0(self) -> float: ...
    @property
    def y0(self) -> float: ...
    @property
    def x1(self) -> float: ...
    @property
    def y1(self) -> float: ...

LIMIAR_LINHA_LARGA = 0.60
MIN_LARGURA_CALHA_PT = 12.0
PROPORCAO_CALHA = 0.03
MIN_PROPORCAO_LINHAS_COLUNA = 0.20
MAX_COLUNAS = 3


def detectar_colunas(
    caixas_linhas: Sequence[tuple[float, float, float, float]],
    largura_pagina: float,
) -> list[tuple[float, float]]:
    """Detecta colunas verticais a partir da projeção horizontal das linhas de texto."""
    largura = max(1.0, float(largura_pagina))
    if not caixas_linhas:
        return [(0.0, largura)]

    linhas_estreitas = [
        c for c in caixas_linhas if (c[2] - c[0]) <= largura * LIMIAR_LINHA_LARGA
    ]
    if len(linhas_estreitas) < 4:
        return [(0.0, largura)]

    n_bins = max(1, int(largura) + 1)
    hist = [0] * n_bins
    for x0, _, x1, _ in linhas_estreitas:
        i0 = max(0, min(n_bins - 1, int(x0)))
        i1 = max(i0, min(n_bins - 1, int(x1)))
        for idx in range(i0, i1 + 1):
            hist[idx] += 1

    min_calha = max(MIN_LARGURA_CALHA_PT, largura * PROPORCAO_CALHA)

    # Identifica trechos vazios internos (entre primeira e última posição ocupada)
    ocupados = [i for i, v in enumerate(hist) if v > 0]
    if not ocupados:
        return [(0.0, largura)]
    inicio_texto, fim_texto = ocupados[0], ocupados[-1]

    calhas: list[tuple[int, int]] = []
    em_vazio = False
    vazio_ini = 0
    for idx in range(inicio_texto, fim_texto + 1):
        if hist[idx] == 0:
            if not em_vazio:
                em_vazio = True
                vazio_ini = idx
        else:
            if em_vazio:
                if (idx - vazio_ini) >= min_calha:
                    calhas.append((vazio_ini, idx))
                em_vazio = False

    if not calhas:
        return [(0.0, largura)]

    # Seleciona até MAX_COLUNAS - 1 maiores calhas que dividam linhas de forma equilibrada
    calhas.sort(key=lambda c: c[1] - c[0], reverse=True)
    cortes = sorted((ini + fim) / 2.0 for ini, fim in calhas[: MAX_COLUNAS - 1])

    limites = [0.0, *cortes, largura]
    colunas = [(limites[i], limites[i + 1]) for i in range(len(limites) - 1)]

    # Valida que cada coluna concentra ao menos MIN_PROPORCAO_LINHAS_COLUNA das linhas estreitas
    contagens = [0] * len(colunas)
    for x0, _, x1, _ in linhas_estreitas:
        cx = (x0 + x1) / 2.0
        for idx, (c0, c1) in enumerate(colunas):
            if c0 <= cx <= c1:
                contagens[idx] += 1
                break

    min_linhas = max(2, int(len(linhas_estreitas) * MIN_PROPORCAO_LINHAS_COLUNA))
    if any(c < min_linhas for c in contagens):
        return [(0.0, largura)]

    return colunas


def atribuir_coluna(
    x0: float,
    x1: float,
    colunas: Sequence[tuple[float, float]],
) -> int:
    """Retorna o índice da coluna com maior sobreposição horizontal com [x0, x1]."""
    if len(colunas) <= 1:
        return 0
    melhor_idx = 0
    melhor_overlap = -1.0
    for idx, (c0, c1) in enumerate(colunas):
        overlap = max(0.0, min(x1, c1) - max(x0, c0))
        if overlap > melhor_overlap:
            melhor_overlap = overlap
            melhor_idx = idx
    return melhor_idx


def _cruza_calha(item: ItemEspacial, colunas: Sequence[tuple[float, float]]) -> bool:
    if len(colunas) <= 1:
        return False
    colunas_tocadas = 0
    for c0, c1 in colunas:
        if min(item.x1, c1) - max(item.x0, c0) > 4.0:
            colunas_tocadas += 1
    return colunas_tocadas >= 2


def ordenar_por_leitura[T: ItemEspacial](
    itens: Sequence[T],
    colunas: Sequence[tuple[float, float]],
) -> list[T]:
    """Ordena itens respeitando faixas horizontais e leitura coluna por coluna."""
    if not itens:
        return []
    if len(colunas) <= 1:
        return sorted(itens, key=lambda i: (i.y0, i.x0))

    largos = sorted([i for i in itens if _cruza_calha(i, colunas)], key=lambda i: (i.y0, i.x0))
    colunados = [i for i in itens if not _cruza_calha(i, colunas)]

    if not largos:
        por_col: list[list[T]] = [[] for _ in colunas]
        for item in colunados:
            por_col[atribuir_coluna(item.x0, item.x1, colunas)].append(item)
        resultado: list[T] = []
        for grupo in por_col:
            grupo.sort(key=lambda i: (i.y0, i.x0))
            resultado.extend(grupo)
        return resultado

    resultado = []
    y_cursor = float("-inf")
    for largo in largos:
        faixa = [i for i in colunados if y_cursor <= i.y0 < largo.y0]
        if faixa:
            por_col = [[] for _ in colunas]
            for item in faixa:
                por_col[atribuir_coluna(item.x0, item.x1, colunas)].append(item)
            for grupo in por_col:
                grupo.sort(key=lambda i: (i.y0, i.x0))
                resultado.extend(grupo)
        resultado.append(largo)
        y_cursor = max(y_cursor, largo.y0)

    restantes = [i for i in colunados if i.y0 >= y_cursor]
    if restantes:
        por_col = [[] for _ in colunas]
        for item in restantes:
            por_col[atribuir_coluna(item.x0, item.x1, colunas)].append(item)
        for grupo in por_col:
            grupo.sort(key=lambda i: (i.y0, i.x0))
            resultado.extend(grupo)

    return resultado


__all__ = [
    "atribuir_coluna",
    "detectar_colunas",
    "ordenar_por_leitura",
]
