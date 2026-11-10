from pathlib import Path

import pymupdf
import pytest

from anotai.adapters.outbound.pdf import ExtratorPDF
from anotai.adapters.outbound.pdf.extrator_pdf import identificar_xrefs_template
from anotai.domain.exceptions.DocumentoInvalido import DocumentoInvalido
from anotai.domain.exceptions.MetodoExtracaoNaoSuportado import MetodoExtracaoNaoSuportado


def _pdf(tmp_path: Path, text: str = "Conteúdo suficiente para extração nativa.") -> Path:
    path = tmp_path / "material.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()
    return path


def test_extracts_native_text_and_bbox(tmp_path: Path) -> None:
    result = ExtratorPDF().extrair(_pdf(tmp_path))

    assert result.paginas[0].texto_nativo.strip()
    assert result.paginas[0].unidades[0].fonte == "native"
    assert result.paginas[0].unidades[0].caixa is not None


def test_normalizes_text_without_changing_original() -> None:
    original = "Título\u00a0  com-\nquebra\u0000 de linha"

    normalizado = ExtratorPDF._normalizar(original)

    assert normalizado == "Título comquebra de linha"
    assert original != normalizado


def test_classifies_native_documental_units(tmp_path: Path) -> None:
    texto = (
        "TÍTULO PRINCIPAL\n"
        "- item da lista\n"
        "Texto de apoio.\n"
        "Figura 1: Diagrama de blocos\n"
        "x = a + b"
    )
    path = _pdf(tmp_path, texto)

    result = ExtratorPDF().extrair(path, "native")

    assert [unidade.tipo for unidade in result.paginas[0].unidades] == [
        "title",
        "group",
        "paragraph",
        "caption",
        "formula",
    ]


def test_extracts_embedded_image_as_document_unit(tmp_path: Path) -> None:
    path = tmp_path / "imagem.pdf"
    imagem = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 100, 100), False)
    imagem.clear_with(0x336699)
    document = pymupdf.open()
    page = document.new_page()
    page.insert_image(pymupdf.Rect(50, 50, 200, 200), pixmap=imagem)
    document.save(path)
    document.close()

    result = ExtratorPDF().extrair(path, "native")
    unidades_imagem = [
        unidade for unidade in result.paginas[0].unidades if unidade.tipo == "figure"
    ]

    assert len(unidades_imagem) == 1
    assert unidades_imagem[0].fonte == "native"
    assert unidades_imagem[0].texto is None
    assert unidades_imagem[0].caixa is not None
    assert unidades_imagem[0].ids_evidencias[0].startswith("image-xref-")


def test_rejects_invalid_file(tmp_path: Path) -> None:
    with pytest.raises(DocumentoInvalido):
        ExtratorPDF().extrair(tmp_path / "missing.pdf")


def test_rejects_unknown_method(tmp_path: Path) -> None:
    with pytest.raises(MetodoExtracaoNaoSuportado):
        ExtratorPDF().extrair(_pdf(tmp_path), "invalid")


def test_does_not_require_ollama_without_visual_elements(tmp_path: Path) -> None:
    path = tmp_path / "empty.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(path)
    document.close()

    result = ExtratorPDF().extrair(path)

    assert result.paginas[0].metodo_extracao == "native"


class FakeAnalyzer:
    modelo = "qwen3-vl:8b"

    def __init__(self) -> None:
        self.imagens: list[bytes] = []

    def analisar(self, imagem: bytes, numero_pagina: int) -> list[dict[str, object]]:
        assert imagem
        assert numero_pagina == 1
        self.imagens.append(imagem)
        return [{"type": "figure", "text": "Conteúdo visual", "bbox": [1, 2, 3, 4]}]


def test_uses_ollama_for_each_embedded_visual_element(tmp_path: Path) -> None:
    path = tmp_path / "visual.pdf"
    imagem = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 100, 100), False)
    imagem.clear_with(0x336699)
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Texto nativo suficiente.")
    page.insert_image(pymupdf.Rect(72, 100, 222, 250), pixmap=imagem)
    document.save(path)
    document.close()

    analyzer = FakeAnalyzer()
    result = ExtratorPDF(analyzer).extrair(path)
    unidades_ocr = [unidade for unidade in result.paginas[0].unidades if unidade.fonte == "ollama"]

    assert len(analyzer.imagens) == 1
    assert result.paginas[0].metodo_extracao == "mixed"
    assert "Conteúdo visual" in result.paginas[0].texto_normalizado
    assert len(unidades_ocr) == 1
    assert unidades_ocr[0].fonte == "ollama"
    assert unidades_ocr[0].texto == "Conteúdo visual"
    assert unidades_ocr[0].ids_evidencias[0].startswith("image-xref-")
    assert unidades_ocr[0].caixa is not None
    assert not [
        unidade
        for unidade in result.paginas[0].unidades
        if unidade.fonte == "native" and unidade.tipo == "figure"
    ]


def test_filters_template_xref_before_ollama(tmp_path: Path) -> None:
    path = tmp_path / "template.pdf"
    imagem = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 100, 100), False)
    imagem.clear_with(0x336699)
    document = pymupdf.open()
    primeira = document.new_page()
    primeira.insert_image(pymupdf.Rect(50, 50, 200, 200), pixmap=imagem)
    xref = primeira.get_images(full=True)[0][0]
    for _ in range(3):
        pagina = document.new_page()
        pagina.insert_image(pymupdf.Rect(50, 50, 200, 200), xref=xref)
    document.save(path)
    document.close()

    documento = pymupdf.open(path)
    assert identificar_xrefs_template(documento) == {xref}
    documento.close()

    analyzer = FakeAnalyzer()
    resultado = ExtratorPDF(analyzer).extrair(path)

    assert analyzer.imagens == []
    assert all(not pagina.unidades for pagina in resultado.paginas)


def test_reuses_visual_analysis_for_equal_image_bytes(tmp_path: Path) -> None:
    path = tmp_path / "cache.pdf"
    imagem = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 100, 100), False)
    imagem.clear_with(0x336699)
    document = pymupdf.open()
    primeira = document.new_page()
    primeira.insert_image(pymupdf.Rect(50, 50, 200, 200), pixmap=imagem)
    xref = primeira.get_images(full=True)[0][0]
    segunda = document.new_page()
    segunda.insert_image(pymupdf.Rect(50, 50, 200, 200), xref=xref)
    document.save(path)
    document.close()

    analyzer = FakeAnalyzer()
    resultado = ExtratorPDF(analyzer).extrair(path)

    assert len(analyzer.imagens) == 1
    assert (
        sum(unidade.eh_decorativa for pagina in resultado.paginas for unidade in pagina.unidades)
        == 0
    )


def test_marks_decorative_visual_units(tmp_path: Path) -> None:
    class DecorativeAnalyzer(FakeAnalyzer):
        def analisar(self, imagem: bytes, numero_pagina: int) -> list[dict[str, object]]:
            self.imagens.append(imagem)
            return [
                {
                    "type": "figure",
                    "text": None,
                    "image_classification": "decorativo",
                }
            ]

    path = tmp_path / "decorativo.pdf"
    imagem = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 100, 100), False)
    imagem.clear_with(0x336699)
    document = pymupdf.open()
    document.new_page().insert_image(pymupdf.Rect(50, 50, 200, 200), pixmap=imagem)
    document.save(path)
    document.close()

    resultado = ExtratorPDF(DecorativeAnalyzer()).extrair(path)

    assert all(
        unidade.eh_decorativa
        for pagina in resultado.paginas
        for unidade in pagina.unidades
        if unidade.tipo == "figure"
    )


def test_rejects_ollama_only_method(tmp_path: Path) -> None:
    with pytest.raises(MetodoExtracaoNaoSuportado):
        ExtratorPDF().extrair(_pdf(tmp_path), "ollama")


def test_orders_units_by_spatial_reading_order(tmp_path: Path) -> None:
    path = tmp_path / "ordem.pdf"
    imagem = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 100, 100), False)
    imagem.clear_with(0x336699)
    document = pymupdf.open()
    page = document.new_page()
    page.insert_image(pymupdf.Rect(50, 30, 200, 180), pixmap=imagem)
    page.insert_text((72, 220), "Texto abaixo da imagem.")
    document.save(path)
    document.close()

    resultado = ExtratorPDF(FakeAnalyzer()).extrair(path)
    unidades = resultado.paginas[0].unidades

    assert [u.fonte for u in unidades] == ["ollama", "native"]
    assert [u.ordem_leitura for u in unidades] == [1, 2]


def test_renders_page_when_vector_drawings_exceed_threshold(tmp_path: Path) -> None:
    path = tmp_path / "vetorial.pdf"
    document = pymupdf.open()
    document.new_page()
    pagina_diagrama = document.new_page()
    for i in range(20):
        pagina_diagrama.draw_rect(pymupdf.Rect(20 + i * 5, 20 + i * 5, 60 + i * 5, 60 + i * 5))
    document.save(path)
    document.close()

    class PageAnalyzer(FakeAnalyzer):
        def analisar(self, imagem: bytes, numero_pagina: int) -> list[dict[str, object]]:
            assert imagem.startswith(b"\x89PNG")
            self.imagens.append(imagem)
            return [{"type": "figure", "text": "Diagrama vetorial extraído"}]

    analyzer = PageAnalyzer()
    resultado = ExtratorPDF(analyzer).extrair(path)

    assert len(analyzer.imagens) == 1
    assert resultado.paginas[1].metodo_extracao == "mixed"
    assert resultado.paginas[1].unidades[0].texto == "Diagrama vetorial extraído"


def test_filters_repeated_template_lines_and_page_numbers_from_units(tmp_path: Path) -> None:
    path = tmp_path / "template_lines.pdf"
    document = pymupdf.open()
    for idx in range(1, 5):
        page = document.new_page()
        page.insert_text((72, 40), "Universidade Federal - Cabeçalho Fixo")
        page.insert_text((72, 120), f"Conteúdo exclusivo da página {idx}.")
        page.insert_text((72, 750), str(idx))
    document.save(path)
    document.close()

    resultado = ExtratorPDF().extrair(path, "native")

    for idx, pagina in enumerate(resultado.paginas, start=1):
        assert "Cabeçalho Fixo" in pagina.texto_nativo
        assert "Cabeçalho Fixo" not in pagina.texto_normalizado
        textos_unidades = [u.texto for u in pagina.unidades if u.texto]
        assert textos_unidades == [f"Conteúdo exclusivo da página {idx}."]


def test_collapses_fragmented_images_into_single_page_render(tmp_path: Path) -> None:
    path = tmp_path / "fragmentado.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 40), "Slide com recortes fragmentados")
    for idx in range(5):
        img = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 100, 100), False)
        img.clear_with(0x112233 + idx * 100)
        x0 = 40 + (idx % 3) * 160
        y0 = 80 + (idx // 3) * 160
        page.insert_image(pymupdf.Rect(x0, y0, x0 + 140, y0 + 140), pixmap=img)
    document.save(path)
    document.close()

    analyzer = FakeAnalyzer()
    resultado = ExtratorPDF(analyzer).extrair(path)

    assert len(analyzer.imagens) == 1
    assert resultado.paginas[0].metodo_extracao == "mixed"
    assert len(resultado.paginas[0].unidades) == 1
    assert resultado.paginas[0].unidades[0].fonte == "ollama"
    assert resultado.paginas[0].unidades[0].ids_evidencias == ["page-render-1"]


def test_rejects_empty_or_encrypted_pdf(tmp_path: Path) -> None:
    vazio = tmp_path / "vazio.pdf"
    vazio.write_bytes(b"")
    with pytest.raises(DocumentoInvalido, match="vazio"):
        ExtratorPDF().extrair(vazio, "native")

    protegido = tmp_path / "protegido.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Segredo")
    doc.save(
        protegido,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="user",
    )
    doc.close()
    with pytest.raises(DocumentoInvalido, match="senha"):
        ExtratorPDF().extrair(protegido, "native")


def test_detects_sections_and_renders_page_with_highlights(tmp_path: Path) -> None:
    from anotai.adapters.outbound.pdf import DestaqueVisual, RenderizadorPaginaPyMuPdf
    from anotai.domain.value_objects.CaixaDelimitadora import CaixaDelimitadora

    path = tmp_path / "secoes.pdf"
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((72, 60), "1. Introdução aos Algoritmos", fontsize=18)
    p1.insert_text((72, 120), "Texto do corpo com fonte normal explicando o conceito.", fontsize=11)
    doc.set_toc([[1, "1. Introdução aos Algoritmos", 1]])
    doc.save(path)
    doc.close()

    resultado = ExtratorPDF().extrair(path, "native")
    assert resultado.proveniencia.configuracao is not None
    assert resultado.proveniencia.configuracao["secoes_detectadas"] == "1"

    png = RenderizadorPaginaPyMuPdf().renderizar(
        path,
        1,
        destaques=[DestaqueVisual(CaixaDelimitadora(50, 40, 400, 150))],
        palavras_chave=["Algoritmos"],
    )
    assert png.startswith(b"\x89PNG")

