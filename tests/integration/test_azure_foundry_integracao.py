import importlib.util
import wave
from pathlib import Path

import pymupdf
import pytest

from anotai.adapters.outbound.azure import ProvedorAzureSpeech
from anotai.adapters.outbound.google import AnalisadorVisualGoogleAIStudio
from anotai.config import Settings


def _modulo_disponivel(nome: str) -> bool:
    try:
        return importlib.util.find_spec(nome) is not None
    except ModuleNotFoundError:
        return False


_SDK_GOOGLE_DISPONIVEL = _modulo_disponivel("google.genai")
_SDK_SPEECH_DISPONIVEL = _modulo_disponivel("azure.cognitiveservices.speech")


def _settings_ambiente() -> Settings:
    return Settings.from_environment()


@pytest.mark.skipif(
    not _SDK_GOOGLE_DISPONIVEL or not _settings_ambiente().google_api_key,
    reason=(
        "SDK google-genai ou chave do Google AI Studio não configurados para teste de integração."
    ),
)
def test_integracao_google_ai_studio_gemma4(tmp_path: Path) -> None:
    cfg = _settings_ambiente()
    doc = pymupdf.open()
    pagina = doc.new_page(width=640, height=360)
    pagina.insert_text((48, 80), "Redes Neurais Convolucionais", fontsize=24)
    pagina.insert_text((48, 130), "Camadas de convolução e pooling", fontsize=16)
    imagem_bytes = pagina.get_pixmap(dpi=150, alpha=False).tobytes("png")
    doc.close()

    analisador = AnalisadorVisualGoogleAIStudio(
        chave=cfg.google_api_key,
        modelo=cfg.google_visual_model,
    )
    unidades = analisador.analisar(imagem_bytes, 1)

    assert len(unidades) >= 1
    assert unidades[0]["image_classification"] == "conteudo"
    assert unidades[0]["text"]


@pytest.mark.skipif(
    not _SDK_SPEECH_DISPONIVEL
    or not _settings_ambiente().azure_speech_key
    or not (_settings_ambiente().azure_speech_region or _settings_ambiente().azure_speech_endpoint),
    reason="Credenciais ou SDK do Azure Speech não configurados para teste de integração.",
)
def test_integracao_azure_speech_wav_silencioso(tmp_path: Path) -> None:
    cfg = _settings_ambiente()
    wav_path = tmp_path / "silencio.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)

    provedor = ProvedorAzureSpeech(
        chave=cfg.azure_speech_key,
        regiao=cfg.azure_speech_region,
        endpoint=cfg.azure_speech_endpoint,
        idioma=cfg.azure_speech_language,
        timestamps_palavras=cfg.azure_speech_word_timestamps,
    )
    resultado = provedor.transcrever(wav_path)
    assert resultado.idioma == cfg.azure_speech_language
    assert isinstance(resultado.segmentos, list)
