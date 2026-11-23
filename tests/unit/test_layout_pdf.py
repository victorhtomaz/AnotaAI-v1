from pathlib import Path

import pymupdf

from anotai.adapters.outbound.pdf import ExtratorPDF


def test_ordena_duas_colunas_com_titulo_largura_total(tmp_path: Path) -> None:
    path = tmp_path / "duas_colunas.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)

    # Título atravessando toda a largura
    page.insert_text((50, 60), "TÍTULO PRINCIPAL DO ARTIGO CIENTÍFICO", fontsize=18)

    # Coluna esquerda (x ~ 50..250)
    for idx in range(5):
        page.insert_text((50, 120 + idx * 25), f"Esquerda linha {idx + 1}.", fontsize=11)

    # Coluna direita (x ~ 330..530) na mesma altura da coluna esquerda
    for idx in range(5):
        page.insert_text((330, 120 + idx * 25), f"Direita linha {idx + 1}.", fontsize=11)

    doc.save(path)
    doc.close()

    resultado = ExtratorPDF().extrair(path, "native")
    textos = [u.texto for u in resultado.paginas[0].unidades if u.texto]

    assert textos[0].startswith("TÍTULO PRINCIPAL")
    pos_esq = next(i for i, t in enumerate(textos) if "Esquerda" in t)
    pos_dir = next(i for i, t in enumerate(textos) if "Direita" in t)
    assert pos_esq < pos_dir
    # Nenhuma linha da direita deve aparecer intercalada antes do fim da esquerda
    ult_esq = max(i for i, t in enumerate(textos) if "Esquerda" in t)
    assert pos_dir > ult_esq


def test_nao_funde_linhas_de_colunas_distintas_na_mesma_altura(tmp_path: Path) -> None:
    path = tmp_path / "nao_funde.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)

    for idx in range(4):
        y = 100 + idx * 14
        page.insert_text((50, y), f"Coluna A {idx + 1}", fontsize=11)
        page.insert_text((340, y), f"Coluna B {idx + 1}", fontsize=11)

    doc.save(path)
    doc.close()

    resultado = ExtratorPDF().extrair(path, "native")
    unidades = [u for u in resultado.paginas[0].unidades if u.texto]

    assert len(unidades) == 2
    assert "Coluna B" not in (unidades[0].texto or "")
    assert "Coluna A" not in (unidades[1].texto or "")
