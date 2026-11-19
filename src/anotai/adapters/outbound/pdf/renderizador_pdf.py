from __future__ import annotations

from pathlib import Path

import pymupdf


class RenderizadorPDFPyMuPDF:
    """Implementação da porta RenderizadorDocumento usando PyMuPDF."""

    def obter_dimensoes_paginas(self, caminho_pdf: Path) -> dict[int, tuple[float, float]]:
        dimensoes: dict[int, tuple[float, float]] = {}
        if not caminho_pdf.is_file():
            return dimensoes

        try:
            with pymupdf.open(caminho_pdf) as pdf:
                for idx, page in enumerate(pdf, start=1):
                    rect = page.rect
                    if rect.width > 0 and rect.height > 0:
                        dimensoes[idx] = (float(rect.width), float(rect.height))
        except Exception:
            dimensoes.clear()
        return dimensoes

    def renderizar_pagina_png(
        self, caminho_pdf: Path, numero_pagina: int, dpi: int = 150
    ) -> bytes:
        with pymupdf.open(caminho_pdf) as pdf:
            if numero_pagina < 1 or numero_pagina > len(pdf):
                raise IndexError(f"Página {numero_pagina} fora do intervalo do PDF.")
            pix = pdf[numero_pagina - 1].get_pixmap(dpi=dpi, alpha=False)
            return pix.tobytes("png")
