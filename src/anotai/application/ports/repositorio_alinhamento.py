from typing import Protocol

from anotai.domain.entities.Alinhamento import Alinhamento


class RepositorioAlinhamento(Protocol):
    def salvar(self, alinhamento: Alinhamento) -> None:
        """Persiste ou atualiza um alinhamento individual de forma idempotente."""
        ...

    def salvar_lote(self, alinhamentos: list[Alinhamento]) -> None:
        """Persiste ou atualiza múltiplos alinhamentos em uma única transação."""
        ...

    def buscar_por_id(self, id_alinhamento: str) -> Alinhamento | None:
        """Busca um alinhamento específico pelo seu ID."""
        ...

    def listar_por_intervalo(
        self, id_intervalo: str, estrategia: str | None = None
    ) -> list[Alinhamento]:
        """Lista alinhamentos associados a um intervalo explicativo específico."""
        ...

    def listar_por_aula(
        self,
        id_aula: str,
        id_documento: str | None = None,
        estrategia: str | None = None,
    ) -> list[Alinhamento]:
        """Lista alinhamentos de uma aula, opcionalmente filtrados por documento e estratégia."""
        ...

    def listar_por_pagina(
        self, id_pagina: str, estrategia: str | None = None
    ) -> list[Alinhamento]:
        """Permite a navegação bidirecional PDF -> áudio através do ID da página."""
        ...

    def listar_por_unidade(
        self, id_unidade: str, estrategia: str | None = None
    ) -> list[Alinhamento]:
        """Permite a navegação bidirecional PDF -> áudio através do ID da unidade documental."""
        ...
