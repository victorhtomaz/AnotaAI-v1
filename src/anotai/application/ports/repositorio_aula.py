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

    def buscar_por_termo(self, termo: str) -> list[tuple[str, str]]:
        """Busca aulas cujo ID ou título contenham o termo informado."""
        ...

    def excluir(self, id_aula: str) -> bool:
        """Remove uma aula e seus dados associados por cascade. Retorna True se removida."""
        ...
