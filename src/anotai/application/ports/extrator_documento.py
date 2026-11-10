from pathlib import Path
from typing import Protocol

from anotai.domain.entities.Documento import Documento


class ExtratorDocumento(Protocol):
    def extrair(self, caminho: Path, metodo: str = "native_then_ocr") -> Documento: ...
