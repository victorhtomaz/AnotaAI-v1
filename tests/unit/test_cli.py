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


def test_fronteira_hexagonal_adaptador_cli() -> None:
    import ast

    import anotai.adapters.inbound.cli.principal as principal_mod

    diretorio_cli = Path(principal_mod.__file__).resolve().parent
    prefixos_proibidos = (
        "anotai.adapters.outbound",
        "pymupdf",
        "fitz",
        "ollama",
    )
    for arquivo_py in sorted(diretorio_cli.glob("*.py")):
        arvore = ast.parse(arquivo_py.read_text(encoding="utf-8"), filename=str(arquivo_py))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                for alias in no.names:
                    assert not alias.name.startswith(prefixos_proibidos), (
                        f"Violação hexagonal em {arquivo_py.name}: import {alias.name}"
                    )
            elif isinstance(no, ast.ImportFrom) and no.module:
                assert not no.module.startswith(prefixos_proibidos), (
                    f"Violação hexagonal em {arquivo_py.name}: from {no.module}"
                )


def test_cli_listar_texto_e_json(tmp_path: Path, capsys) -> None:
    import json

    from anotai.adapters.outbound.persistence import (
        RepositorioAlinhamentoSQLite,
        RepositorioAulaSQLite,
        RepositorioDocumentoSQLite,
    )
    from anotai.config import Settings
    from anotai.domain.entities import Alinhamento, Documento, PaginaDocumento
    from anotai.domain.value_objects import ProvenienciaDocumento

    banco = tmp_path / "anotai.sqlite"
    doc = Documento(
        id_documento="doc-cli-1",
        uri_origem=str(tmp_path / "slides.pdf"),
        titulo="Slides CLI",
        paginas=[
            PaginaDocumento(
                id_pagina="doc-cli-1-p1",
                numero_pagina=1,
                texto_nativo="Texto",
                texto_normalizado="Texto",
                metodo_extracao="native",
            )
        ],
        versao_processamento="v1",
        proveniencia=ProvenienciaDocumento(
            uri_origem=str(tmp_path / "slides.pdf"),
            metodo_extracao="native",
            versao_pipeline="v1",
        ),
    )
    aula = Aula(
        id_aula="aula-cli-1",
        titulo="Aula CLI",
        uri_origem=str(tmp_path / "aula.wav"),
        caminho_arquivo=tmp_path / "aula.wav",
        metadados=MetadadosAudio(duracao=12.0, taxa_amostragem=16000, canais=1, formato="wav"),
        segmentos=[],
        intervalos=[
            IntervaloExplicativo(
                id_intervalo="int-cli-1",
                id_aula="aula-cli-1",
                texto="Trecho",
                intervalo=IntervaloTempo(0.0, 12.0),
                ordem=1,
            )
        ],
    )
    alin = Alinhamento(
        id_alinhamento="align-cli-1",
        id_aula="aula-cli-1",
        id_documento="doc-cli-1",
        id_intervalo="int-cli-1",
        ids_paginas=["doc-cli-1-p1"],
        status="aligned",
        tipo_relacao="direct",
        confianca=0.9,
        estrategia="hierarchical_hmm",
    )

    RepositorioDocumentoSQLite(banco).salvar(doc)
    RepositorioAulaSQLite(banco).salvar(aula)
    RepositorioAlinhamentoSQLite(banco).salvar(alin)

    settings = Settings(database_path=str(banco))
    with patch(
        "anotai.adapters.inbound.cli.principal.Settings.from_environment",
        return_value=settings,
    ):
        assert main(["listar"]) == 0
        out_txt = capsys.readouterr().out
        assert "doc-cli-1" in out_txt
        assert "aula-cli-1" in out_txt
        assert "hierarchical_hmm" in out_txt

        assert main(["listar", "--format", "json"]) == 0
        dados = json.loads(capsys.readouterr().out)
        assert dados["aulas"][0]["id"] == "aula-cli-1"
        assert dados["documentos"][0]["id"] == "doc-cli-1"
        assert dados["alinhamentos"]["aula-cli-1"][0]["id"] == "align-cli-1"


def test_cli_atalho_dois_arquivos_aciona_alinhar() -> None:
    with patch(
        "anotai.adapters.inbound.cli.principal.alinhar_aula", return_value=0
    ) as mock_alinhar:
        codigo = main(["aula.wav", "slides.pdf"])
        assert codigo == 0
        assert mock_alinhar.call_count == 1
        args_chamados = mock_alinhar.call_args[0][0]
        assert args_chamados.subcomando == "alinhar"
        assert args_chamados.id_aula == "aula.wav"
        assert args_chamados.id_documento == "slides.pdf"


def test_cli_opcoes_nuvem_pdf_e_transcrever(tmp_path: Path, capsys) -> None:
    pdf_path = tmp_path / "slides.pdf"
    pdf_path.touch()
    audio_path = tmp_path / "aula.wav"
    audio_path.touch()

    from anotai.config import Settings

    settings_sem_chaves = Settings(database_path=str(tmp_path / "banco.sqlite"))
    with patch(
        "anotai.adapters.inbound.cli.principal.Settings.from_environment",
        return_value=settings_sem_chaves,
    ):
        cod_pdf = main(["pdf", str(pdf_path), "--visual-provider", "google_ai_studio"])
        assert cod_pdf == 1
        assert "ANOTAI_GOOGLE_API_KEY" in capsys.readouterr().err

        cod_asr = main(
            ["transcrever", str(audio_path), "--provider", "azure_speech", "--language", "en-US"]
        )
        assert cod_asr == 1
        assert "ANOTAI_AZURE_SPEECH" in capsys.readouterr().err

        cod_buscar = main(
            [
                "buscar",
                "aula-1",
                "doc-1",
                "--strategy",
                "embedding",
                "--embedding-provider",
                "google_ai_studio",
            ]
        )
        assert cod_buscar == 1

        cod_alinhar = main(
            [
                "alinhar",
                "aula-1",
                "doc-1",
                "--base-strategy",
                "hybrid",
                "--embedding-provider",
                "google_ai_studio",
            ]
        )
        assert cod_alinhar == 1


def test_bootstrap_rejeita_provedores_desconhecidos_ou_sem_credenciais() -> None:
    from anotai.bootstrap import criar_analisador_visual, criar_provedor_transcricao
    from anotai.config import Settings
    from anotai.domain.exceptions import ErroAnaliseVisual, ErroTranscricao

    cfg = Settings()
    with pytest.raises(ErroAnaliseVisual, match="não suportado"):
        criar_analisador_visual(
            cfg,
            cfg.visual_model,
            temperatura=0.0,
            seed=42,
            pensar=False,
            provedor="desconhecido",
        )

    with pytest.raises(ErroTranscricao, match="não suportado"):
        criar_provedor_transcricao(
            modelo="base",
            dispositivo="cpu",
            tipo_computacao="int8",
            alinhar_fonemas=False,
            settings=cfg,
            provedor="desconhecido",
        )
