from pathlib import Path

from anotai.application.ports.extrator_documento import ExtratorDocumento
from anotai.application.ports.repositorio_documento import RepositorioDocumento
from anotai.domain.entities import Documento


class ImportarDocumento:
    def __init__(
        self,
        extrator: ExtratorDocumento,
        repositorio: RepositorioDocumento | None = None,
    ) -> None:
        self._extrator = extrator
        self._repositorio = repositorio

    def executar(self, caminho: Path, metodo: str = "native_then_ocr") -> Documento:
        documento = self._extrator.extrair(caminho, metodo)
        if self._repositorio is not None:
            self._repositorio.salvar(documento)
        return documento
