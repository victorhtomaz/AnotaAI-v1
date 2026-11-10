from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

PADRAO_NUMERACAO = re.compile(
    r"^(?:cap(?:í|i)tulo|se(?:ç|c)(?:ã|a)o|parte)\s+\d+[\s:.-]*"
    r"|^\d+(?:\.\d+)*[\s:.-]+",
    re.IGNORECASE,
)
PREFIXO_SLIDE = re.compile(
    r"^(?:slide|p(?:á|a)gina)\s*\d+\s*[:.-]\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SecaoBrutaPdf:
    titulo: str
    nivel: int
    pagina_inicial: int
    pagina_final: int


def normalizar_texto(texto: str) -> str:
    return " ".join(texto.lower().split())


def normalizar_titulo_secao(titulo: str) -> str:
    titulo_normalizado = PREFIXO_SLIDE.sub("", titulo.strip())
    return " ".join(titulo_normalizado.split())


def normalizar_conteudo_extraido(texto: str) -> str:
    texto = unicodedata.normalize("NFKC", texto).replace("\u00a0", " ")
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.category(caractere).startswith("C") or caractere in "\n\t"
    )
    texto = re.sub(r"(?<=\w)-[\t ]*\n[\t ]*(?=\w)", "", texto)
    return re.sub(r"\s+", " ", texto).strip()


def limpar_texto_pagina(texto_pagina: str, linhas_template: set[str]) -> str:
    linhas_uteis = [
        limpa
        for linha in (texto_pagina or "").splitlines()
        if (limpa := linha.strip()) and not limpa.isdigit() and limpa not in linhas_template
    ]
    return normalizar_conteudo_extraido("\n".join(linhas_uteis))


__all__ = [
    "PADRAO_NUMERACAO",
    "PREFIXO_SLIDE",
    "SecaoBrutaPdf",
    "limpar_texto_pagina",
    "normalizar_conteudo_extraido",
    "normalizar_texto",
    "normalizar_titulo_secao",
]
