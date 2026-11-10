from typing import Protocol

from anotai.domain.entities import Anotacao


class RepositorioAnotacao(Protocol):
    def salvar(self, anotacao: Anotacao) -> None:
        """Persiste ou atualiza uma anotação de ground truth de forma idempotente."""
        ...

    def salvar_lote(self, anotacoes: list[Anotacao]) -> None:
        """Persiste ou atualiza múltiplas anotações de ground truth em lote."""
        ...

    def buscar_por_id(self, id_anotacao: str) -> Anotacao | None:
        """Busca uma anotação pelo seu ID."""
        ...

    def listar_por_aula(
        self,
        id_aula: str,
        id_documento: str | None = None,
        versao: str | None = None,
    ) -> list[Anotacao]:
        """Lista anotações de uma aula, opcionalmente filtradas por documento e versão."""
        ...

    def listar_por_intervalo(
        self, id_intervalo: str, versao: str | None = None
    ) -> list[Anotacao]:
        """Lista anotações associadas a um intervalo explicativo."""
        ...
