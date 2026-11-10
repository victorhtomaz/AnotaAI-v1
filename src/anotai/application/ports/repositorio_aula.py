from typing import Any, Protocol

from anotai.domain.entities import Aula


class RepositorioAula(Protocol):
    def salvar(self, aula: Aula, carga_bruta_asr: dict[str, Any] | None = None) -> None:
        """Persiste a aula, seus segmentos, intervalos e opcionalmente os dados brutos de ASR."""
        ...

    def buscar_por_id(self, id_aula: str) -> Aula | None:
        """Recupera uma aula completa por seu identificador."""
        ...

    def listar(self) -> list[Aula]:
        """Lista todas as aulas cadastradas."""
        ...
