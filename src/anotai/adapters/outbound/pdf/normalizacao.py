from __future__ import annotations

import re
import unicodedata


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
    "limpar_texto_pagina",
    "normalizar_conteudo_extraido",
]
