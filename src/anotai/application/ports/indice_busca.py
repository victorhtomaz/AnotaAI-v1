from collections.abc import Sequence
from typing import Protocol


class IndiceBusca(Protocol):
    def indexar(self, itens: Sequence[tuple[str, str]]) -> None:
        """Indexa uma sequência de itens representados por pares (id_item, texto)."""
        ...

    def consultar_lote(
        self, consultas: Sequence[str], top_k: int = 5
    ) -> list[list[tuple[str, float]]]:
        """Consulta textos em lote e retorna os top_k (id_item, pontuacao) por consulta.

        As pontuações retornadas devem estar normalizadas no intervalo [0.0, 1.0] e
        ordenadas de forma decrescente de relevância.
        """
        ...
