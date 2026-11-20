from typing import Protocol

from anotai.domain.entities import Documento


class RepositorioDocumento(Protocol):
    def salvar(self, documento: Documento) -> None:
        """Persiste um documento completo, suas páginas, unidades e proveniência."""
        ...

    def buscar_por_id(self, id_documento: str) -> Documento | None:
        """Recupera um documento completo por seu identificador estável."""
        ...

    def listar(self) -> list[Documento]:
        """Lista todos os documentos persistidos."""
        ...

    def existe(self, id_documento: str) -> bool:
        """Verifica se um documento já foi persistido no banco."""
        ...

    def buscar_por_termo(self, termo: str) -> list[tuple[str, str]]:
        """Busca documentos cujo ID ou título contenham o termo informado."""
        ...

    def excluir(self, id_documento: str) -> bool:
        """Remove um documento e seus dados associados por cascade. Retorna True se removido."""
        ...
