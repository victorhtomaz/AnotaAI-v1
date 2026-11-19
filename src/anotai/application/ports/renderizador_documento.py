from __future__ import annotations

from pathlib import Path
from typing import Protocol


class RenderizadorDocumento(Protocol):
    """Porta para inspeção de dimensões e renderização de páginas de documentos."""

    def obter_dimensoes_paginas(self, caminho_pdf: Path) -> dict[int, tuple[float, float]]: ...

    def renderizar_pagina_png(
        self, caminho_pdf: Path, numero_pagina: int, dpi: int = 150
    ) -> bytes: ...
