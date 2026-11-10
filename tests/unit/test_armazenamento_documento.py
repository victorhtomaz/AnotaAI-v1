from pathlib import Path

from anotai.adapters.outbound.persistence import ArmazenamentoDocumento
from anotai.domain.entities.Documento import Documento, PaginaDocumento, UnidadeDocumento
from anotai.domain.value_objects.CaixaDelimitadora import CaixaDelimitadora
from anotai.domain.value_objects.ProvenienciaDocumento import ProvenienciaDocumento


def test_salva_documento_processado_sem_alterar_origem(tmp_path: Path) -> None:
    origem = tmp_path / "material.pdf"
    origem.write_bytes(b"pdf original")
    documento = Documento(
        id_documento="doc-teste",
        uri_origem=str(origem),
        titulo="material",
        paginas=[
            PaginaDocumento(
                id_pagina="doc-teste-page-1",
                numero_pagina=1,
                texto_nativo="Texto",
                texto_normalizado="Texto",
                metodo_extracao="native",
                unidades=[
                    UnidadeDocumento(
                        id_unidade="doc-teste-page-1-unit-1",
                        id_documento="doc-teste",
                        id_pagina="doc-teste-page-1",
                        tipo="block",
                        texto="Texto",
                        ordem_leitura=1,
                        caixa=CaixaDelimitadora(1, 2, 3, 4),
                        fonte="native",
                    )
                ],
            )
        ],
        versao_processamento="fase1-v1",
        proveniencia=ProvenienciaDocumento(
            uri_origem=str(origem),
            metodo_extracao="native",
            versao_pipeline="fase1-v1",
            configuracao={"minimo_caracteres": "20"},
            executado_em="2026-11-09T00:00:00+00:00",
        ),
    )

    banco = tmp_path / "processados" / "anotai.sqlite"
    destino = ArmazenamentoDocumento(banco).salvar(documento)

    assert destino.exists()
    assert ArmazenamentoDocumento(banco).existe("doc-teste")
    assert origem.read_bytes() == b"pdf original"
