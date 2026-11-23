from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pymupdf as fitz

from anotai.domain.entities import UnidadeDocumento
from anotai.domain.value_objects import CaixaDelimitadora

from .imagens import ImagemBrutaPdf, RenderPaginaPdf
from .layout import atribuir_coluna, detectar_colunas, ordenar_por_leitura
from .normalizacao import normalizar_conteudo_extraido
from .regioes import RegiaoTabela, RegiaoVetorial, ponto_em_caixas

PADRAO_BULLET = re.compile(
    r"^([•◦▪‣–\-*·]|(\d+|[a-zA-Z])[\.\)])\s+",
    re.UNICODE,
)
PADRAO_LEGENDA = re.compile(
    r"^(Figura|Fig\.|Tabela|Quadro|Grafico|Gráfico)\s+\d+",
    re.IGNORECASE,
)
PADRAO_FORMULA = re.compile(r"(?:[=∑∫√^]|\\(?:frac|sum|int))")


def _eh_bullet(texto: str) -> bool:
    return bool(PADRAO_BULLET.match(texto.strip()))


def _eh_legenda(texto: str) -> bool:
    return bool(PADRAO_LEGENDA.match(texto.strip()))


def _eh_formula(texto: str) -> bool:
    return bool(PADRAO_FORMULA.search(texto))


def _eh_titulo_caixa_alta(texto: str) -> bool:
    limpo = texto.strip()
    return (
        bool(limpo)
        and limpo.isupper()
        and len(limpo) <= 120
        and len(limpo.split()) <= 10
        and not limpo.endswith((".", ":", ";"))
    )


def segmentar_unidades_pagina(
    pagina: fitz.Page,
    documento_id: str,
    pagina_id: str,
    linhas_template: set[str],
    imagens: Sequence[ImagemBrutaPdf],
    render_pagina: RenderPaginaPdf | None,
    tabelas: Sequence[RegiaoTabela] = (),
    regioes_vetoriais: Sequence[RegiaoVetorial] = (),
    colunas: Sequence[tuple[float, float]] | None = None,
) -> list[UnidadeDocumento]:
    """Segmenta o conteúdo visual e textual de uma página em unidades estruturadas com bbox."""
    # Caso especial: Slide puramente visual ou página escaneada/colapsada de página inteira
    if render_pagina is not None:
        return [
            UnidadeDocumento(
                id_unidade=f"{pagina_id}-unit-1",
                id_documento=documento_id,
                id_pagina=pagina_id,
                tipo="figure",
                texto=None,
                ordem_leitura=1,
                caixa=render_pagina.caixa,
                fonte="native",
                ids_evidencias=[render_pagina.evidencia],
            )
        ]

    dados_dict = pagina.get_text("dict", sort=False) or {}
    blocos_raw = dados_dict.get("blocks", [])

    caixas_tabelas = [t.caixa for t in tabelas]
    caixas_vetoriais = [r.caixa for r in regioes_vetoriais]
    rotulos_vetoriais: dict[int, list[str]] = {idx: [] for idx in range(len(regioes_vetoriais))}

    tamanhos_fonte: list[float] = []
    linhas_candidatas: list[dict[str, Any]] = []

    for b in blocos_raw:
        if b.get("type") != 0:
            continue
        for linha_dict in b.get("lines", []):
            spans = linha_dict.get("spans", [])
            texto_linha = "".join(s.get("text", "") for s in spans).strip()
            if not texto_linha or texto_linha in linhas_template:
                continue
            if texto_linha.isdigit():
                continue

            bbox_raw = linha_dict.get("bbox", (0.0, 0.0, 0.0, 0.0))
            bx0, by0, bx1, by1 = (round(float(x), 2) for x in bbox_raw[:4])
            cx = (bx0 + bx1) / 2.0
            cy = (by0 + by1) / 2.0

            if ponto_em_caixas(cx, cy, caixas_tabelas):
                continue

            em_regiao_vetorial = False
            for idx_rv, caixa_rv in enumerate(caixas_vetoriais):
                if caixa_rv.x0 <= cx <= caixa_rv.x1 and caixa_rv.y0 <= cy <= caixa_rv.y1:
                    rotulos_vetoriais[idx_rv].append(texto_linha)
                    em_regiao_vetorial = True
                    break
            if em_regiao_vetorial:
                continue

            sizes = [float(s.get("size", 12.0)) for s in spans if s.get("text", "").strip()]
            tam_medio = sum(sizes) / len(sizes) if sizes else 12.0
            tamanhos_fonte.append(tam_medio)

            linhas_candidatas.append(
                {
                    "texto": texto_linha,
                    "bbox": (bx0, by0, bx1, by1),
                    "tam_fonte": tam_medio,
                }
            )

    largura_pagina = float(pagina.rect.width) if pagina.rect else 612.0
    colunas_efetivas = (
        list(colunas)
        if colunas is not None
        else detectar_colunas([item["bbox"] for item in linhas_candidatas], largura_pagina)
    )
    mediana_fonte = sorted(tamanhos_fonte)[len(tamanhos_fonte) // 2] if tamanhos_fonte else 12.0

    unidades_texto: list[dict[str, Any]] = []
    bloco_atual: list[dict[str, Any]] = []

    def fechar_bloco_atual() -> None:
        if not bloco_atual:
            return
        texto_bruto = "\n".join(item["texto"] for item in bloco_atual)
        texto_unido = normalizar_conteudo_extraido(texto_bruto)
        if not texto_unido:
            bloco_atual.clear()
            return

        x0 = min(item["bbox"][0] for item in bloco_atual)
        y0 = min(item["bbox"][1] for item in bloco_atual)
        x1 = max(item["bbox"][2] for item in bloco_atual)
        y1 = max(item["bbox"][3] for item in bloco_atual)
        tam_medio = sum(item["tam_fonte"] for item in bloco_atual) / len(bloco_atual)

        primeiro_texto = bloco_atual[0]["texto"]
        if _eh_legenda(primeiro_texto):
            tipo = "caption"
        elif _eh_bullet(primeiro_texto):
            tipo = "group"
        elif _eh_formula(texto_unido):
            tipo = "formula"
        elif (
            tam_medio >= mediana_fonte * 1.25
            or (len(bloco_atual) == 1 and _eh_titulo_caixa_alta(primeiro_texto))
        ) and len(unidades_texto) < 2:
            tipo = "title"
        else:
            tipo = "paragraph"

        unidades_texto.append(
            {
                "tipo": tipo,
                "texto": texto_unido,
                "caixa": CaixaDelimitadora(x0, y0, x1, y1),
                "y0": y0,
                "x0": x0,
                "evidencias": [],
            }
        )
        bloco_atual.clear()

    linhas_por_coluna: list[list[dict[str, Any]]] = [[] for _ in colunas_efetivas]
    for item in linhas_candidatas:
        idx_col = atribuir_coluna(item["bbox"][0], item["bbox"][2], colunas_efetivas)
        linhas_por_coluna[idx_col].append(item)

    for grupo_col in linhas_por_coluna:
        grupo_col.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
        for item in grupo_col:
            txt = item["texto"]
            eh_inicio_bullet = _eh_bullet(txt)
            eh_inicio_legenda = _eh_legenda(txt)
            eh_linha_formula = _eh_formula(txt)

            deve_quebrar = False
            if bloco_atual:
                ultimo = bloco_atual[-1]
                salto_vertical = item["bbox"][1] - ultimo["bbox"][3]
                altura_linha = max(1.0, ultimo["bbox"][3] - ultimo["bbox"][1])
                variacao_fonte = abs(item["tam_fonte"] - ultimo["tam_fonte"]) / max(
                    1.0, ultimo["tam_fonte"]
                )
                x_overlap = min(item["bbox"][2], ultimo["bbox"][2]) - max(
                    item["bbox"][0], ultimo["bbox"][0]
                )

                quebra_espaco = salto_vertical > altura_linha * 1.3
                quebra_horizontal = x_overlap <= 0.0
                quebra_pos_titulo = len(bloco_atual) == 1 and _eh_titulo_caixa_alta(
                    ultimo["texto"]
                )
                quebra_pos_bullet = _eh_bullet(bloco_atual[0]["texto"]) and not eh_inicio_bullet
                quebra_pos_legenda = _eh_legenda(bloco_atual[0]["texto"])
                if (
                    eh_inicio_bullet
                    or eh_inicio_legenda
                    or eh_linha_formula
                    or quebra_espaco
                    or quebra_horizontal
                    or variacao_fonte > 0.20
                    or quebra_pos_titulo
                    or quebra_pos_bullet
                    or quebra_pos_legenda
                ):
                    deve_quebrar = True

            if deve_quebrar:
                fechar_bloco_atual()
            bloco_atual.append(item)

        fechar_bloco_atual()

    unidades_todas: list[dict[str, Any]] = list(unidades_texto)
    for tab in tabelas:
        unidades_todas.append(
            {
                "tipo": "table",
                "texto": tab.texto,
                "caixa": tab.caixa,
                "y0": tab.caixa.y0,
                "x0": tab.caixa.x0,
                "evidencias": [tab.evidencia],
            }
        )
    for idx_rv, rv in enumerate(regioes_vetoriais):
        rotulos = normalizar_conteudo_extraido(" ".join(rotulos_vetoriais.get(idx_rv, [])))
        unidades_todas.append(
            {
                "tipo": "figure",
                "texto": rotulos or None,
                "caixa": rv.caixa,
                "y0": rv.caixa.y0,
                "x0": rv.caixa.x0,
                "evidencias": [rv.evidencia],
            }
        )
    for img in imagens:
        unidades_todas.append(
            {
                "tipo": "figure",
                "texto": None,
                "caixa": img.caixa,
                "y0": img.caixa.y0,
                "x0": img.caixa.x0,
                "evidencias": [img.evidencia],
            }
        )

    @dataclass(slots=True)
    class _ItemOrdenavel:
        dados: dict[str, Any]
        x0: float
        y0: float
        x1: float
        y1: float

    ordenaveis = [
        _ItemOrdenavel(
            dados=u,
            x0=u["caixa"].x0,
            y0=u["caixa"].y0,
            x1=u["caixa"].x1,
            y1=u["caixa"].y1,
        )
        for u in unidades_todas
    ]
    unidades_ordenadas = [item.dados for item in ordenar_por_leitura(ordenaveis, colunas_efetivas)]

    resultado: list[UnidadeDocumento] = []
    for ordem, u in enumerate(unidades_ordenadas, start=1):
        resultado.append(
            UnidadeDocumento(
                id_unidade=f"{pagina_id}-unit-{ordem}",
                id_documento=documento_id,
                id_pagina=pagina_id,
                tipo=u["tipo"],
                texto=u["texto"],
                ordem_leitura=ordem,
                caixa=u["caixa"],
                fonte="native",
                ids_evidencias=list(u["evidencias"]),
            )
        )

    return resultado


__all__ = ["segmentar_unidades_pagina"]
