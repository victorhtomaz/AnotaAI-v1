from pathlib import Path

from anotai.application.ports.extrator_documento import ExtratorDocumento
from anotai.domain.entities.Documento import Documento


class ImportarDocumento:
    def __init__(self, extrator: ExtratorDocumento) -> None:
        self._extrator = extrator

    def executar(self, caminho: Path, metodo: str = "native_then_ocr") -> Documento:
        return self._extrator.extrair(caminho, metodo)
