from collections.abc import Sequence
from typing import Protocol


class ProvedorEmbedding(Protocol):
    def gerar_embeddings(self, textos: Sequence[str]) -> list[list[float]]:
        """Gera vetores densos para uma sequência de textos na mesma ordem de entrada."""
        ...
