from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anotai.adapters.inbound.cli.principal import main
from anotai.domain.entities.Aula import Aula
from anotai.domain.entities.IntervaloExplicativo import IntervaloExplicativo
from anotai.domain.entities.SegmentoTranscricao import SegmentoTranscricao
from anotai.domain.value_objects.IntervaloTempo import IntervaloTempo
from anotai.domain.value_objects.MetadadosAudio import MetadadosAudio


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
