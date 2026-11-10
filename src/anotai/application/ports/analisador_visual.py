from typing import Any, Protocol


class AnalisadorVisual(Protocol):
    def analisar(self, imagem: bytes, numero_pagina: int) -> list[dict[str, Any]]: ...
