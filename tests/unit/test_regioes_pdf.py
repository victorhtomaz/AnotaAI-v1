from pathlib import Path

import pymupdf

from anotai.adapters.outbound.pdf import ExtratorPDF


def test_detecta_tabela_nativa_e_exclui_celulas_dos_paragrafos(tmp_path: Path) -> None:
    path = tmp_path / "tabela.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)

    page.insert_text((50, 60), "Texto introdutório antes da tabela.", fontsize=12)

    # Desenha grade 3x3 (x=50..500, y=100..250)
    cols = [50, 200, 350, 500]
    rows = [100, 150, 200, 250]
    for y in rows:
        page.draw_line((cols[0], y), (cols[-1], y))
    for x in cols:
        page.draw_line((x, rows[0]), (x, rows[-1]))

    dados = [
        ["Modelo", "Recall", "F1"],
        ["BM25", "70%", "65%"],
        ["HMM", "85%", "82%"],
    ]
    for r_idx, row in enumerate(dados):
        for c_idx, val in enumerate(row):
            page.insert_text((cols[c_idx] + 10, rows[r_idx] + 30), val, fontsize=11)

    doc.save(path)
    doc.close()

    resultado = ExtratorPDF().extrair(path, "native")
    unidades = resultado.paginas[0].unidades
    tabelas = [u for u in unidades if u.tipo == "table"]
    paragrafos = [u for u in unidades if u.tipo == "paragraph"]

    assert len(tabelas) == 1
    assert "Modelo | Recall | F1" in (tabelas[0].texto or "")
    assert "BM25 | 70% | 65%" in (tabelas[0].texto or "")
    assert tabelas[0].fonte == "native"
    assert all("BM25" not in (p.texto or "") for p in paragrafos)
    assert resultado.proveniencia.configuracao["tabelas_nativas"] == 1


def test_detecta_regiao_vetorial_em_pagina_com_texto_e_envia_recorte_ao_vlm(
    tmp_path: Path,
) -> None:
    path = tmp_path / "grafico_vetorial.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)

    # Texto longo (> 80 chars) para não cair no fallback de página inteira
    page.insert_text(
        (50, 60),
        "Esta página contém texto suficiente para análise nativa e um gráfico vetorial abaixo.",
        fontsize=12,
    )
    page.insert_text(
        (50, 80),
        "O gráfico ilustra a evolução das métricas experimentais ao longo das épocas.",
        fontsize=12,
    )

    # Desenha um gráfico vetorial conectado (> 8 primitivos, área entre 4% e 85%)
    page.draw_line((75, 195), (75, 425))
    page.draw_line((75, 425), (380, 425))
    for i in range(10):
        x0 = 80 + i * 28
        page.draw_rect(pymupdf.Rect(x0, 200, x0 + 25, 420), color=(0, 0, 0), fill=(0.2, 0.4, 0.8))

    doc.save(path)
    doc.close()

    recortes_recebidos: list[bytes] = []

    class FakeVLM:
        modelo = "fake-vlm"
        prompt = "p"
        provedor = "ollama"
        fonte_unidade = "ollama"

        def validar_modelo_visual(self) -> None:
            return None

        def analisar(self, imagem: bytes, numero_pagina: int) -> list[dict[str, object]]:
            recortes_recebidos.append(imagem)
            return [{"type": "graph", "text": "Gráfico de barras com 10 séries."}]

    resultado = ExtratorPDF(FakeVLM()).extrair(path, "native_then_ocr")
    graficos = [u for u in resultado.paginas[0].unidades if u.tipo == "graph"]

    assert len(recortes_recebidos) >= 1
    assert len(graficos) >= 1
    assert graficos[0].fonte == "ollama"
    assert graficos[0].caixa is not None
    assert graficos[0].caixa.y0 >= 190.0
    assert resultado.proveniencia.configuracao["regioes_vetoriais"] >= 1


def test_moldura_simples_nao_vira_tabela_nem_regiao_vetorial(tmp_path: Path) -> None:
    path = tmp_path / "moldura.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=400)
    page.draw_rect(pymupdf.Rect(20, 20, 580, 380))
    page.insert_text((60, 100), "Slide com moldura simples e texto.", fontsize=16)
    doc.save(path)
    doc.close()

    resultado = ExtratorPDF().extrair(path, "native")
    unidades = resultado.paginas[0].unidades

    assert all(u.tipo != "table" for u in unidades)
    assert resultado.proveniencia.configuracao["tabelas_nativas"] == 0
    assert resultado.proveniencia.configuracao["regioes_vetoriais"] == 0
