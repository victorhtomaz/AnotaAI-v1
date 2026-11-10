from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median

import pymupdf as fitz

from .normalizacao import (
    PADRAO_NUMERACAO,
    PREFIXO_SLIDE,
    SecaoBrutaPdf,
    normalizar_texto,
    normalizar_titulo_secao,
)


@dataclass(frozen=True, slots=True)
class _LinhaFormatada:
    pagina: int
    texto: str
    y: float
    altura: float
    tamanho_fonte: float
    negrito: bool
    primeira_linha_bloco: bool


@dataclass(slots=True)
class _CandidatoSecao:
    titulo: str
    pagina: int
    y: float
    tamanho_fonte: float
    negrito: bool
    pontuacao: int
    veio_de_prefixo_slide: bool = False
    nivel: int = 1


def _extrair_linhas_formatadas(
    doc: fitz.Document,
) -> tuple[list[_LinhaFormatada], list[float]]:
    linhas: list[_LinhaFormatada] = []
    tamanhos_fonte: list[float] = []

    for numero_pagina in range(doc.page_count):
        pagina = doc.load_page(numero_pagina)
        dados = pagina.get_text("dict")
        for bloco in dados.get("blocks", []):
            if bloco.get("type") != 0:
                continue
            for numero_linha, linha in enumerate(bloco.get("lines", [])):
                spans = linha.get("spans", [])
                texto = " ".join(
                    str(span.get("text", "")).strip()
                    for span in spans
                    if str(span.get("text", "")).strip()
                ).strip()
                if not texto or not spans:
                    continue
                tamanhos_validos = [
                    float(span.get("size", 0)) for span in spans if float(span.get("size", 0)) > 0
                ]
                if not tamanhos_validos:
                    continue
                tamanhos_fonte.extend(tamanhos_validos)
                linhas.append(
                    _LinhaFormatada(
                        pagina=numero_pagina + 1,
                        texto=texto,
                        y=float(linha.get("bbox", (0, 0, 0, 0))[1]),
                        altura=pagina.rect.height,
                        tamanho_fonte=median(tamanhos_validos),
                        negrito=any(int(span.get("flags", 0)) & 16 for span in spans),
                        primeira_linha_bloco=numero_linha == 0,
                    )
                )
    return linhas, tamanhos_fonte


def _detectar_candidatos_secao(doc: fitz.Document) -> list[_CandidatoSecao]:
    linhas, tamanhos_fonte = _extrair_linhas_formatadas(doc)
    if not linhas or not tamanhos_fonte:
        return []

    fonte_corpo = median(tamanhos_fonte)
    ocorrencias: dict[str, set[int]] = {}
    for linha in linhas:
        texto = normalizar_titulo_secao(linha.texto)
        chave = normalizar_texto(texto)
        ocorrencias.setdefault(chave, set()).add(linha.pagina)

    candidatos: list[_CandidatoSecao] = []
    for linha in linhas:
        texto = normalizar_titulo_secao(linha.texto)
        veio_de_prefixo_slide = bool(PREFIXO_SLIDE.match(linha.texto))
        chave = normalizar_texto(normalizar_titulo_secao(texto))
        palavras = texto.split()
        pontuacao = 0

        if not 3 <= len(texto) <= 80 or len(palavras) > 10:
            continue
        if len(ocorrencias[chave]) >= 3 and not veio_de_prefixo_slide:
            continue
        if re.fullmatch(r"(?:p(?:á|a)gina\s*)?\d+", texto, re.IGNORECASE):
            continue
        if re.search(r"(?:https?://|www\.|@\w+)", texto, re.IGNORECASE):
            continue
        if linha.tamanho_fonte >= fonte_corpo * 1.15:
            pontuacao += 2
        if linha.tamanho_fonte >= fonte_corpo * 1.35:
            pontuacao += 1
        if linha.negrito:
            pontuacao += 2
        if linha.primeira_linha_bloco:
            pontuacao += 1
        if linha.y <= linha.altura * 0.25:
            pontuacao += 1
        if not re.search(r"[.;:!?]$", texto):
            pontuacao += 1
        if PADRAO_NUMERACAO.search(texto):
            pontuacao += 2
        if len(palavras) <= 8:
            pontuacao += 1
        if re.search(r"[.!?].*[a-zá-ú]", texto, re.IGNORECASE):
            pontuacao -= 2

        if pontuacao >= 5:
            candidatos.append(
                _CandidatoSecao(
                    titulo=texto,
                    pagina=linha.pagina,
                    y=linha.y,
                    tamanho_fonte=linha.tamanho_fonte,
                    negrito=linha.negrito,
                    pontuacao=pontuacao,
                    veio_de_prefixo_slide=veio_de_prefixo_slide,
                )
            )

    candidatos.sort(key=lambda candidato: (candidato.pagina, candidato.y))
    unicos: list[_CandidatoSecao] = []
    vistos: set[tuple[int, str]] = set()
    titulos_slide_vistos: set[str] = set()
    for candidato in candidatos:
        titulo_normalizado = normalizar_texto(normalizar_titulo_secao(candidato.titulo))
        if candidato.veio_de_prefixo_slide:
            if titulo_normalizado in titulos_slide_vistos:
                continue
            titulos_slide_vistos.add(titulo_normalizado)
        chave_unica = (candidato.pagina, titulo_normalizado)
        if chave_unica not in vistos:
            vistos.add(chave_unica)
            unicos.append(candidato)
    return unicos


def _inferir_niveis(candidatos: list[_CandidatoSecao]) -> None:
    menor_fonte = min(item.tamanho_fonte for item in candidatos)
    for candidato in candidatos:
        correspondencia = PADRAO_NUMERACAO.search(candidato.titulo)
        if correspondencia and re.match(r"\d", candidato.titulo):
            prefixo = candidato.titulo.split(maxsplit=1)[0].rstrip(".:-")
            candidato.nivel = max(1, min(6, prefixo.count(".") + 1))
        elif candidato.tamanho_fonte >= 1.35 * menor_fonte:
            candidato.nivel = 1
        else:
            candidato.nivel = 2


def detectar_secoes_tipograficas(
    doc: fitz.Document,
    total_paginas: int,
) -> list[SecaoBrutaPdf]:
    candidatos = _detectar_candidatos_secao(doc)
    if not candidatos:
        return []
    _inferir_niveis(candidatos)

    secoes: list[SecaoBrutaPdf] = []
    for indice, candidato in enumerate(candidatos):
        pagina_final = total_paginas
        for proximo in candidatos[indice + 1 :]:
            if proximo.nivel <= candidato.nivel:
                pagina_final = max(candidato.pagina, proximo.pagina - 1)
                break
        secoes.append(
            SecaoBrutaPdf(
                titulo=candidato.titulo,
                nivel=candidato.nivel,
                pagina_inicial=candidato.pagina,
                pagina_final=pagina_final,
            )
        )
    return secoes


__all__ = ["detectar_secoes_tipograficas"]
