import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anotai.adapters.outbound.audio.inspetor_ffmpeg import InspetorFFmpeg
from anotai.domain.exceptions import AudioInvalido


def test_inspetor_ffmpeg_arquivo_inexistente(tmp_path: Path) -> None:
    inspetor = InspetorFFmpeg()
    with pytest.raises(AudioInvalido, match="arquivo de áudio não encontrado"):
        inspetor.inspecionar(tmp_path / "inexistente.wav")


def test_inspetor_ffmpeg_inspecionar_sucesso(tmp_path: Path) -> None:
    audio_file = tmp_path / "audio.mp3"
    audio_file.touch()

    ffprobe_output = {
        "format": {
            "duration": "125.432",
            "format_name": "mp3",
            "bit_rate": "128000",
        },
        "streams": [
            {
                "codec_name": "mp3",
                "sample_rate": "44100",
                "channels": 2,
            }
        ],
    }

    mock_run = MagicMock()
    mock_run.stdout = json.dumps(ffprobe_output)

    with patch("subprocess.run", return_value=mock_run):
        inspetor = InspetorFFmpeg()
        meta = inspetor.inspecionar(audio_file)

        assert meta.duracao == 125.432
        assert meta.taxa_amostragem == 44100
        assert meta.canais == 2
        assert meta.codec == "mp3"
        assert meta.formato == "mp3"
        assert meta.taxa_bits == 128000


def test_inspetor_ffmpeg_inspecionar_mkv_com_tags_matroska(tmp_path: Path) -> None:
    mkv_file = tmp_path / "aula.mkv"
    mkv_file.touch()

    # Formato Matroska com duracao no formato HH:MM:SS.mmm em tags
    ffprobe_output = {
        "format": {
            "format_name": "matroska,webm",
            "bit_rate": "150000",
            "tags": {
                "DURATION": "01:15:30.500000000",
            },
        },
        "streams": [
            {
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
            }
        ],
    }

    mock_run = MagicMock()
    mock_run.stdout = json.dumps(ffprobe_output)

    with patch("subprocess.run", return_value=mock_run):
        inspetor = InspetorFFmpeg()
        meta = inspetor.inspecionar(mkv_file)

        # 1h (3600) + 15m (900) + 30.5s = 4530.5
        assert meta.duracao == 4530.5
        assert meta.taxa_amostragem == 48000
        assert meta.canais == 2
        assert meta.codec == "aac"
        assert meta.formato == "matroska,webm"


def test_inspetor_ffmpeg_extrair_wav_mono_16k(tmp_path: Path) -> None:
    origem = tmp_path / "video.mkv"
    origem.touch()
    destino = tmp_path / "processado" / "audio.wav"

    mock_run = MagicMock()

    with patch("subprocess.run", return_value=mock_run) as patched_run:
        inspetor = InspetorFFmpeg()
        resultado = inspetor.extrair_wav_mono_16k(origem, destino)

        assert resultado == destino
        patched_run.assert_called_once()
        cmd = patched_run.call_args[0][0]
        assert "-vn" in cmd
        assert "-sn" in cmd
        assert "-dn" in cmd
        assert "-ar" in cmd
        assert "16000" in cmd
        assert "-ac" in cmd
        assert "1" in cmd
