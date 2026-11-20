from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anotai.adapters.outbound.audio.provedor_whisperx import ProvedorWhisperX
from anotai.domain.exceptions import ErroTranscricao


def test_resolver_dispositivo_e_tipo_cpu() -> None:
    disp, tipo = ProvedorWhisperX._resolver_dispositivo_e_tipo("cpu", "float16")
    assert disp == "cpu"
    assert tipo == "int8"


def test_resolver_dispositivo_cuda_indisponivel_fallback_cpu() -> None:
    with patch("torch.cuda.is_available", return_value=False):
        disp, tipo = ProvedorWhisperX._resolver_dispositivo_e_tipo("cuda", "float16")
    assert disp == "cpu"
    assert tipo == "int8"


def test_provedor_whisperx_arquivo_inexistente(tmp_path: Path) -> None:
    provedor = ProvedorWhisperX(modelo="tiny", dispositivo="cpu")
    with pytest.raises(ErroTranscricao, match="não encontrado"):
        provedor.transcrever(tmp_path / "inexistente.wav")


def test_provedor_whisperx_transcricao_mockada(tmp_path: Path) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.touch()

    mock_model = MagicMock()
    mock_model.transcribe.return_value = {
        "language": "pt",
        "segments": [
            {
                "text": "Olá mundo do AnotaAI.",
                "start": 0.5,
                "end": 3.2,
                "score": 0.94,
                "words": [
                    {"word": "Olá", "start": 0.5, "end": 0.9, "score": 0.96},
                    {"word": "mundo", "start": 1.0, "end": 1.5, "score": 0.93},
                ],
            }
        ],
    }

    with (
        patch("whisperx.load_model", return_value=mock_model),
        patch("whisperx.load_audio", return_value=MagicMock()),
    ):
        provedor = ProvedorWhisperX(modelo="tiny", dispositivo="cpu", tipo_computacao="int8")
        resultado = provedor.transcrever(audio_path)

        assert resultado.idioma == "pt"
        assert len(resultado.segmentos) == 1
        assert resultado.segmentos[0].texto == "Olá mundo do AnotaAI."
        assert resultado.segmentos[0].inicio == 0.5
        assert resultado.segmentos[0].fim == 3.2
        assert resultado.segmentos[0].confianca == 0.94
        assert len(resultado.segmentos[0].palavras) == 2
        assert resultado.carga_bruta["language"] == "pt"
