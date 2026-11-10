from pathlib import Path

from anotai.domain.entities.Documento import Documento

from .repositorio_documento import RepositorioDocumento


class ArmazenamentoDocumento:
    """Fachada de persistência SQLite para documentos processados."""

    def __init__(self, caminho_banco: Path) -> None:
        self._repositorio = RepositorioDocumento(caminho_banco)

    def salvar(self, documento: Documento) -> Path:
        self._repositorio.salvar(documento)
        return self._repositorio.caminho_banco

    def existe(self, documento_id: str) -> bool:
        return self._repositorio.existe(documento_id)
