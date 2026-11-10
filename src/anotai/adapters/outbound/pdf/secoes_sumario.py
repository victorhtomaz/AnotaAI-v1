from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .normalizacao import (
    SecaoBrutaPdf,
    normalizar_texto,
    normalizar_titulo_secao,
)


def extrair_secoes_do_sumario(
    toc: Sequence[Sequence[Any]],
    total_paginas: int,
) -> list[SecaoBrutaPdf]:
    entradas_toc: list[tuple[int, str, int]] = []
    ultima_entrada_toc: tuple[int, str, int] | None = None

    for item in toc:
        nivel = int(item[0])
        titulo = normalizar_titulo_secao(str(item[1]))
        pag_ini = max(1, min(total_paginas, int(item[2])))
        if not titulo:
            continue

        entrada_atual = (max(1, nivel), titulo, pag_ini)
        if ultima_entrada_toc is not None:
            nivel_anterior, titulo_anterior, pag_anterior = ultima_entrada_toc
            mesma_secao = (
                nivel_anterior == entrada_atual[0]
                and normalizar_texto(titulo_anterior) == normalizar_texto(titulo)
                and pag_ini <= pag_anterior + 1
            )
            if mesma_secao:
                ultima_entrada_toc = entrada_atual
                continue

        entradas_toc.append(entrada_atual)
        ultima_entrada_toc = entrada_atual

    secoes: list[SecaoBrutaPdf] = []
    for idx_toc, (nivel, titulo, pag_ini) in enumerate(entradas_toc):
        pag_fim = total_paginas
        for prox_nivel, _, prox_pag_ini in entradas_toc[idx_toc + 1 :]:
            if prox_nivel <= nivel:
                pag_fim = max(pag_ini, prox_pag_ini - 1)
                break
        secoes.append(
            SecaoBrutaPdf(
                titulo=titulo,
                nivel=nivel,
                pagina_inicial=pag_ini,
                pagina_final=min(total_paginas, pag_fim),
            )
        )
    return secoes


__all__ = ["extrair_secoes_do_sumario"]
