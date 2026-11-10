from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anotai.adapters.inbound.cli.principal import main
from anotai.domain.entities import Aula, IntervaloExplicativo, SegmentoTranscricao
from anotai.domain.value_objects import IntervaloTempo, MetadadosAudio


def test_cli_help(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    capturado = capsys.readouterr()
    assert "AnotaAI" in capturado.out
    assert "transcrever" in capturado.out
    assert "pdf" in capturado.out
    assert "exibir" in capturado.out


def test_cli_transcrever_chamada(tmp_path: Path, capsys) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.touch()

    aula_fake = Aula(
        id_aula="aula-teste-1",
        titulo="Aula Teste",
        uri_origem=str(audio_path),
        caminho_arquivo=audio_path,
        metadados=MetadadosAudio(duracao=15.0, taxa_amostragem=16000, canais=1, formato="wav"),
        segmentos=[
            SegmentoTranscricao(
                id_segmento="seg-1",
                id_aula="aula-teste-1",
                texto="Fala inicial.",
                intervalo=IntervaloTempo(0.0, 5.0),
                ordem=1,
            )
        ],
        intervalos=[
            IntervaloExplicativo(
                id_intervalo="inter-1",
                id_aula="aula-teste-1",
                texto="Fala inicial.",
                intervalo=IntervaloTempo(0.0, 5.0),
                ordem=1,
                ids_segmentos=["seg-1"],
            )
        ],
        idioma="pt",
    )

    with patch(
        "anotai.adapters.inbound.cli.principal.TranscreverAula.executar",
        return_value=aula_fake,
    ):
        codigo = main(["transcrever", str(audio_path), "--format", "text"])
        assert codigo == 0
        out = capsys.readouterr().out
        assert "ID da Aula: aula-teste-1" in out
        assert "Fala inicial." in out


def test_cli_exibir_aula(tmp_path: Path, capsys) -> None:
    aula_fake = Aula(
        id_aula="aula-teste-2",
        titulo="Aula para Exibir",
        uri_origem=str(tmp_path / "teste.wav"),
        caminho_arquivo=tmp_path / "teste.wav",
        metadados=MetadadosAudio(duracao=10.0, taxa_amostragem=16000, canais=1, formato="wav"),
        segmentos=[],
        intervalos=[
            IntervaloExplicativo(
                id_intervalo="inter-1",
                id_aula="aula-teste-2",
                texto="Trecho explicado.",
                intervalo=IntervaloTempo(0.0, 10.0),
                ordem=1,
            )
        ],
    )

    mock_repo = MagicMock()
    mock_repo.buscar_por_id.return_value = aula_fake

    with patch(
        "anotai.adapters.inbound.cli.principal.RepositorioAulaSQLite",
        return_value=mock_repo,
    ):
        codigo = main(["exibir", "aula-teste-2", "--intervalo", "1"])
        assert codigo == 0
        out = capsys.readouterr().out
        assert "Visualizando Intervalo Específico #1" in out
        assert "Trecho explicado." in out


def test_cli_pdf_sucesso(tmp_path: Path, capsys) -> None:
    pdf_path = tmp_path / "material.pdf"
    pdf_path.touch()

    from anotai.domain.entities import Documento, PaginaDocumento, UnidadeDocumento
    from anotai.domain.value_objects import CaixaDelimitadora, ProvenienciaDocumento

    doc_fake = Documento(
        id_documento="doc-teste-pdf",
        uri_origem=str(pdf_path),
        titulo="Material Teste",
        paginas=[
            PaginaDocumento(
                id_pagina="doc-teste-pdf-p1",
                numero_pagina=1,
                texto_nativo="Texto nativo",
                texto_normalizado="Texto nativo",
                metodo_extracao="native",
                unidades=[
                    UnidadeDocumento(
                        id_unidade="doc-teste-pdf-p1-u1",
                        id_documento="doc-teste-pdf",
                        id_pagina="doc-teste-pdf-p1",
                        tipo="paragraph",
                        texto="Texto nativo",
                        ordem_leitura=1,
                        caixa=CaixaDelimitadora(10, 10, 100, 50),
                        fonte="native",
                    )
                ],
            )
        ],
        versao_processamento="v1",
        proveniencia=ProvenienciaDocumento(
            uri_origem=str(pdf_path), metodo_extracao="native", versao_pipeline="v1"
        ),
    )

    with patch(
        "anotai.adapters.inbound.cli.comando_pdf.ImportarDocumento.executar",
        return_value=doc_fake,
    ):
        codigo = main(["pdf", str(pdf_path), "--method", "native"])
        assert codigo == 0
        out = capsys.readouterr().out
        assert "doc-teste-pdf" in out
        assert '"pages": 1' in out
        assert '"units": 1' in out


def test_cli_pdf_erro_processamento(tmp_path: Path, capsys) -> None:
    pdf_path = tmp_path / "nao_existe.pdf"

    from anotai.domain.exceptions import DocumentoInvalido

    with patch(
        "anotai.adapters.inbound.cli.comando_pdf.ImportarDocumento.executar",
        side_effect=DocumentoInvalido("Arquivo inválido"),
    ):
        codigo = main(["pdf", str(pdf_path)])
        assert codigo == 1
        err = capsys.readouterr().err
        assert "Erro ao processar PDF: Arquivo inválido" in err


def test_cli_pdf_erro_integridade(tmp_path: Path, capsys) -> None:
    pdf_path = tmp_path / "corrompido.pdf"
    pdf_path.touch()

    from anotai.domain.exceptions import ErroIntegridade

    with patch(
        "anotai.adapters.inbound.cli.comando_pdf.ImportarDocumento.executar",
        side_effect=ErroIntegridade("Página duplicada detectada"),
    ):
        codigo = main(["pdf", str(pdf_path)])
        assert codigo == 1
        err = capsys.readouterr().err
        assert "Erro ao processar PDF: Página duplicada detectada" in err


def test_cli_transcrever_erro_audio(tmp_path: Path, capsys) -> None:
    audio_path = tmp_path / "audio_invalido.mp3"
    audio_path.touch()

    from anotai.domain.exceptions import AudioInvalido

    with patch(
        "anotai.adapters.inbound.cli.comando_transcrever.TranscreverAula.executar",
        side_effect=AudioInvalido("Codec não suportado"),
    ):
        codigo = main(["transcrever", str(audio_path)])
        assert codigo == 1
        err = capsys.readouterr().err
        assert "Erro na transcrição de áudio: Codec não suportado" in err


def test_cli_transcrever_erro_integridade(tmp_path: Path, capsys) -> None:
    audio_path = tmp_path / "audio_duplicado.wav"
    audio_path.touch()

    from anotai.domain.exceptions import ErroIntegridade

    with patch(
        "anotai.adapters.inbound.cli.comando_transcrever.TranscreverAula.executar",
        side_effect=ErroIntegridade("Aula com ID duplicado"),
    ):
        codigo = main(["transcrever", str(audio_path)])
        assert codigo == 1
        err = capsys.readouterr().err
        assert "Erro na transcrição de áudio: Aula com ID duplicado" in err


def test_cli_exibir_intervalo_inexistente(tmp_path: Path, capsys) -> None:
    aula_fake = Aula(
        id_aula="aula-teste-3",
        titulo="Aula Inspecao",
        uri_origem=str(tmp_path / "teste.wav"),
        caminho_arquivo=tmp_path / "teste.wav",
        metadados=MetadadosAudio(duracao=10.0, taxa_amostragem=16000, canais=1, formato="wav"),
        segmentos=[],
        intervalos=[
            IntervaloExplicativo(
                id_intervalo="inter-1",
                id_aula="aula-teste-3",
                texto="Trecho único.",
                intervalo=IntervaloTempo(0.0, 10.0),
                ordem=1,
            )
        ],
    )

    mock_repo = MagicMock()
    mock_repo.buscar_por_id.return_value = aula_fake

    with patch(
        "anotai.adapters.inbound.cli.principal.RepositorioAulaSQLite",
        return_value=mock_repo,
    ):
        codigo = main(["exibir", "aula-teste-3", "--intervalo", "99"])
        assert codigo == 1
        err = capsys.readouterr().err
        assert "Intervalo explicativo #99 não encontrado na aula." in err
