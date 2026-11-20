import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from anotai.adapters.outbound.azure import ProvedorAzureSpeech
from anotai.domain.exceptions import ErroTranscricao


class FakeEventoSinal:
    def __init__(self) -> None:
        self._callbacks: list[object] = []

    def connect(self, cb: object) -> None:
        self._callbacks.append(cb)

    def disparar(self, evt: object) -> None:
        for cb in self._callbacks:
            cb(evt)


class FakeFuturo:
    def get(self) -> None:
        return None


class FakeSpeechConfig:
    def __init__(self, *, subscription: str, region: str = "", endpoint: str = "") -> None:
        self.subscription = subscription
        self.region = region
        self.endpoint = endpoint
        self.speech_recognition_language = ""
        self.output_format = None
        self.word_timestamps_solicitado = False

    def request_word_level_timestamps(self) -> None:
        self.word_timestamps_solicitado = True


class FakeRecognizer:
    def __init__(
        self,
        speech_config: FakeSpeechConfig,
        audio_config: object,
        eventos: list[tuple[str, object]],
    ) -> None:
        self.speech_config = speech_config
        self.audio_config = audio_config
        self._eventos = eventos
        self.recognized = FakeEventoSinal()
        self.canceled = FakeEventoSinal()
        self.session_stopped = FakeEventoSinal()
        self.parou = False

    def start_continuous_recognition_async(self) -> FakeFuturo:
        for nome, evt in self._eventos:
            if nome == "recognized":
                self.recognized.disparar(evt)
            elif nome == "canceled":
                self.canceled.disparar(evt)
            elif nome == "session_stopped":
                self.session_stopped.disparar(evt)
        return FakeFuturo()

    def stop_continuous_recognition_async(self) -> FakeFuturo:
        self.parou = True
        return FakeFuturo()


def _construir_fake_sdk(
    eventos: list[tuple[str, object]],
) -> tuple[SimpleNamespace, list[FakeRecognizer]]:
    instancias: list[FakeRecognizer] = []

    def _criar_recognizer(speech_config: FakeSpeechConfig, audio_config: object) -> FakeRecognizer:
        rec = FakeRecognizer(speech_config, audio_config, eventos)
        instancias.append(rec)
        return rec

    sdk = SimpleNamespace(
        SpeechConfig=FakeSpeechConfig,
        audio=SimpleNamespace(AudioConfig=lambda filename: SimpleNamespace(filename=filename)),
        SpeechRecognizer=_criar_recognizer,
        OutputFormat=SimpleNamespace(Detailed="Detailed"),
        ResultReason=SimpleNamespace(RecognizedSpeech="RecognizedSpeech", NoMatch="NoMatch"),
        CancellationReason=SimpleNamespace(Error="Error", EndOfStream="EndOfStream"),
        CancellationDetails=SimpleNamespace(
            from_result=lambda res: getattr(res, "cancellation_details", None)
        ),
    )
    return sdk, instancias


def test_transcreve_continuo_converte_ticks_e_palavras(tmp_path: Path) -> None:
    audio_path = tmp_path / "aula.wav"
    audio_path.write_bytes(b"RIFF")

    payload_seg1 = {
        "Offset": 5_000_000,  # 0.5s
        "Duration": 27_000_000,  # 2.7s -> end 3.2s
        "NBest": [
            {
                "Display": "Olá turma do AnotaAI.",
                "Confidence": 0.9512,
                "Words": [
                    {
                        "Word": "Olá",
                        "Offset": 5_000_000,
                        "Duration": 4_000_000,
                        "Confidence": 0.97,
                    },
                    {
                        "Word": "turma",
                        "Offset": 10_000_000,
                        "Duration": 6_000_000,
                        "Confidence": 0.93,
                    },
                ],
            }
        ],
    }
    payload_seg2 = {
        "Offset": 35_000_000,  # 3.5s
        "Duration": 15_000_000,  # 1.5s -> end 5.0s
        "NBest": [{"Display": "Hoje veremos redes neurais.", "Confidence": 0.89}],
    }

    eventos = [
        (
            "recognized",
            SimpleNamespace(
                result=SimpleNamespace(
                    reason="RecognizedSpeech",
                    json=json.dumps(payload_seg1),
                    text="Olá turma do AnotaAI.",
                )
            ),
        ),
        (
            "recognized",
            SimpleNamespace(
                result=SimpleNamespace(
                    reason="RecognizedSpeech",
                    json=json.dumps(payload_seg2),
                    text="Hoje veremos redes neurais.",
                )
            ),
        ),
        (
            "canceled",
            SimpleNamespace(
                result=SimpleNamespace(
                    cancellation_details=SimpleNamespace(
                        reason="EndOfStream", error_code="", error_details=""
                    )
                )
            ),
        ),
        ("session_stopped", SimpleNamespace()),
    ]
    sdk, instancias = _construir_fake_sdk(eventos)
    provedor = ProvedorAzureSpeech(
        chave="chave-secreta-123",
        regiao="francecentral",
        idioma="pt-BR",
        timestamps_palavras=True,
        speech_sdk=sdk,
    )

    resultado = provedor.transcrever(audio_path)

    assert len(instancias) == 1
    assert instancias[0].parou is True
    assert instancias[0].speech_config.speech_recognition_language == "pt-BR"
    assert instancias[0].speech_config.word_timestamps_solicitado is True

    assert resultado.idioma == "pt-BR"
    assert len(resultado.segmentos) == 2

    s1 = resultado.segmentos[0]
    assert s1.texto == "Olá turma do AnotaAI."
    assert s1.inicio == 0.5
    assert s1.fim == 3.2
    assert s1.confianca == 0.9512
    assert s1.palavras == [
        {"word": "Olá", "start": 0.5, "end": 0.9, "score": 0.97},
        {"word": "turma", "start": 1.0, "end": 1.6, "score": 0.93},
    ]

    s2 = resultado.segmentos[1]
    assert s2.inicio == 3.5
    assert s2.fim == 5.0
    assert resultado.carga_bruta["provider"] == "azure_speech"
    assert resultado.carga_bruta["region"] == "francecentral"
    assert len(resultado.carga_bruta["segments"]) == 2


def test_erro_cancelamento_nao_vaza_chave_secreta(tmp_path: Path) -> None:
    audio_path = tmp_path / "aula.wav"
    audio_path.write_bytes(b"RIFF")

    chave_secreta = "segredo-super-sensivel"
    eventos = [
        (
            "canceled",
            SimpleNamespace(
                result=SimpleNamespace(
                    cancellation_details=SimpleNamespace(
                        reason="Error",
                        error_code="AuthenticationFailure",
                        error_details=f"Invalid key {chave_secreta}",
                    )
                )
            ),
        )
    ]
    sdk, instancias = _construir_fake_sdk(eventos)
    provedor = ProvedorAzureSpeech(chave=chave_secreta, regiao="eastus", speech_sdk=sdk)

    with pytest.raises(ErroTranscricao, match="AuthenticationFailure") as exc_info:
        provedor.transcrever(audio_path)

    assert chave_secreta not in str(exc_info.value)
    assert instancias[0].parou is True


def test_valida_arquivo_inexistente_e_credenciais_ausentes(tmp_path: Path) -> None:
    provedor = ProvedorAzureSpeech(chave="k", regiao="eastus")
    with pytest.raises(ErroTranscricao, match="não encontrado"):
        provedor.transcrever(tmp_path / "faltando.wav")

    audio_path = tmp_path / "ok.wav"
    audio_path.write_bytes(b"RIFF")
    provedor_sem_credenciais = ProvedorAzureSpeech(chave="", regiao="")
    with pytest.raises(ErroTranscricao, match="Credenciais"):
        provedor_sem_credenciais.transcrever(audio_path)


def test_suporta_inicializacao_por_endpoint(tmp_path: Path) -> None:
    audio_path = tmp_path / "aula.wav"
    audio_path.write_bytes(b"RIFF")
    eventos = [("session_stopped", SimpleNamespace())]
    sdk, instancias = _construir_fake_sdk(eventos)

    provedor = ProvedorAzureSpeech(
        chave="k",
        endpoint="https://meu-recurso.cognitiveservices.azure.com/",
        speech_sdk=sdk,
    )
    resultado = provedor.transcrever(audio_path)

    assert resultado.segmentos == []
    assert instancias[0].speech_config.endpoint == "https://meu-recurso.cognitiveservices.azure.com/"
