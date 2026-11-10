from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz

from anotai.domain.value_objects.CaixaDelimitadora import CaixaDelimitadora


@dataclass(frozen=True, slots=True)
class DestaqueVisual:
    caixa: CaixaDelimitadora
    principal: bool = True


class RenderizadorPaginaPyMuPdf:
    """Renderiza páginas em PNG e desenha sobreposições visuais sem alterar o arquivo original."""

    COR_PRINCIPAL = (1.0, 0.75, 0.0)  # Âmbar
    COR_SECUNDARIA = (0.20, 0.60, 1.0)  # Azul suave
    BORDA_PRINCIPAL = (0.85, 0.55, 0.0)
    BORDA_SECUNDARIA = (0.10, 0.40, 0.85)

    def renderizar(
        self,
        caminho_pdf: str | Path,
        numero_pagina: int,
        *,
        destaques: Sequence[DestaqueVisual] = (),
        palavras_chave: Sequence[str] = (),
        destacar_apenas_palavras: bool = True,
        dpi: int = 150,
    ) -> bytes:
        caminho = Path(caminho_pdf)
        if not caminho.is_file():
            raise FileNotFoundError(f"Arquivo PDF não encontrado: {caminho_pdf}")

        conteudo = caminho.read_bytes()
        with fitz.open(stream=conteudo, filetype="pdf") as doc:
            if numero_pagina < 1 or numero_pagina > doc.page_count:
                raise ValueError(
                    f"Número de página {numero_pagina} fora do intervalo [1, {doc.page_count}]"
                )

            pagina = doc.load_page(numero_pagina - 1)
            palavras_limpas = [p.strip() for p in palavras_chave if p and p.strip()]
            total_palavras_destacadas = 0

            if palavras_limpas:
                for p_termo in palavras_limpas:
                    if destaques:
                        for d in destaques:
                            ret_clip = (
                                fitz.Rect(d.caixa.x0, d.caixa.y0, d.caixa.x1, d.caixa.y1)
                                & pagina.rect
                            )
                            if ret_clip.is_empty:
                                continue
                            matches = pagina.search_for(p_termo, clip=ret_clip)
                            for m in matches:
                                if not m.is_empty:
                                    pagina.draw_rect(
                                        m,
                                        color=self.BORDA_PRINCIPAL,
                                        fill=self.COR_PRINCIPAL,
                                        fill_opacity=0.60,
                                        width=1.5,
                                    )
                                    total_palavras_destacadas += 1
                    else:
                        matches = pagina.search_for(p_termo)
                        for m in matches:
                            if not m.is_empty:
                                pagina.draw_rect(
                                    m,
                                    color=self.BORDA_PRINCIPAL,
                                    fill=self.COR_PRINCIPAL,
                                    fill_opacity=0.60,
                                    width=1.5,
                                )
                                total_palavras_destacadas += 1

            if total_palavras_destacadas == 0 or not destacar_apenas_palavras:
                for d in destaques:
                    ret = (
                        fitz.Rect(d.caixa.x0, d.caixa.y0, d.caixa.x1, d.caixa.y1) & pagina.rect
                    )
                    if ret.is_empty:
                        continue

                    cor_fill = self.COR_PRINCIPAL if d.principal else self.COR_SECUNDARIA
                    cor_borda = self.BORDA_PRINCIPAL if d.principal else self.BORDA_SECUNDARIA
                    opacidade = 0.35 if total_palavras_destacadas == 0 else 0.08

                    pagina.draw_rect(
                        ret,
                        color=cor_borda,
                        fill=cor_fill,
                        fill_opacity=opacidade,
                        width=2.0 if d.principal else 1.2,
                    )

            pix = pagina.get_pixmap(dpi=dpi, alpha=False)
            return pix.tobytes("png")


__all__ = ["DestaqueVisual", "RenderizadorPaginaPyMuPdf"]
