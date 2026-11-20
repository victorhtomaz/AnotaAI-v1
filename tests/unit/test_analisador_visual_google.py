from types import SimpleNamespace

import pytest

from anotai.adapters.outbound.google import AnalisadorVisualGoogleAIStudio
from anotai.domain.exceptions import ErroAnaliseVisual


class ErroApiGoogleFake(Exception):
    def __init__(self, message: str, *, code: int, status: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message


def _resposta_sdk_fake(texto: str, *, thought_prefix: str | None = None) -> object:
    partes: list[object] = []
    if thought_prefix is not None:
        partes.append(SimpleNamespace(text=thought_prefix, thought=True))
    partes.append(SimpleNamespace(text=texto, thought=False))
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=partes))],
        text=texto,
    )


def _construir_fake_sdk(
    resposta_ou_sequencia: object,
) -> tuple[SimpleNamespace, dict[str, object]]:
    registro: dict[str, object] = {"chamadas": []}

    class FakeHttpOptions:
        def __init__(self, **kwargs: object) -> None:
            registro["http_options"] = kwargs

    class FakeGenerateContentConfig:
        def __init__(self, **kwargs: object) -> None:
            registro["config"] = kwargs

    class FakePart:
        @staticmethod
        def from_bytes(*, data: bytes, mime_type: str) -> dict[str, object]:
            return {"data": data, "mime_type": mime_type}

    class FakeModels:
        def generate_content(
            self, *, model: str, contents: list[object], config: object
        ) -> object:
            registro["model"] = model
            registro["contents"] = contents
            registro["config_obj"] = config
            registro["chamadas"].append(model)  # type: ignore[union-attr]
            if isinstance(resposta_ou_sequencia, list):
                item = resposta_ou_sequencia.pop(0)
            else:
                item = resposta_ou_sequencia
            if isinstance(item, Exception):
                raise item
            return item

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            registro["client_kwargs"] = kwargs
            self.models = FakeModels()

    sdk = SimpleNamespace(
        Client=FakeClient,
        types=SimpleNamespace(
            HttpOptions=FakeHttpOptions,
            GenerateContentConfig=FakeGenerateContentConfig,
            Part=FakePart,
        ),
    )
    return sdk, registro


def test_analisa_imagem_com_sdk_google_genai_e_gemma4() -> None:
    resposta = _resposta_sdk_fake(
        '{"tipo": "conteudo", "units": ['
        '{"type": "graph", "text": "Gráfico de convergência do gradiente descendente."},'
        '{"type": "formula", "text": "L(theta) = 1/N * sum((y - y_hat)^2)"}'
        "]}",
        thought_prefix="Raciocínio interno que deve ser ignorado",
    )
    sdk, registro = _construir_fake_sdk(resposta)
    analisador = AnalisadorVisualGoogleAIStudio(
        chave="chave-google-teste",
        temperatura=0.1,
        genai_sdk=sdk,
    )

    resultado = analisador.analisar(b"\x89PNG\r\n\x1a\nconteudo", 1)

    assert registro["client_kwargs"]["api_key"] == "chave-google-teste"  # type: ignore[index]
    assert registro["http_options"] == {"timeout": 60000}
    assert registro["model"] == "gemma-4-31b-it"
    assert registro["config"] == {"temperature": 0.1}
    contents = registro["contents"]
    assert contents[0] == {"data": b"\x89PNG\r\n\x1a\nconteudo", "mime_type": "image/png"}  # type: ignore[index]
    assert contents[1] == analisador.prompt  # type: ignore[index]

    assert len(resultado) == 2
    assert resultado[0] == {
        "type": "graph",
        "text": "Gráfico de convergência do gradiente descendente.",
        "image_classification": "conteudo",
    }
    assert resultado[1]["type"] == "formula"


def test_aceita_json_em_bloco_markdown_e_classifica_decorativo() -> None:
    sdk, registro = _construir_fake_sdk(
        _resposta_sdk_fake('```json\n{"tipo": "decorativo", "units": []}\n```')
    )
    analisador = AnalisadorVisualGoogleAIStudio(chave="k", genai_sdk=sdk)

    resultado = analisador.analisar(b"\xff\xd8\xffjpeg", 2)

    assert registro["contents"][0]["mime_type"] == "image/jpeg"  # type: ignore[index]
    assert resultado == [{"type": "figure", "text": None, "image_classification": "decorativo"}]


@pytest.mark.parametrize(
    ("status_code", "mensagem"),
    [
        (401, "Unauthorized"),
        (403, "Permission denied"),
        (400, "API key not valid. Please pass a valid API key. API_KEY_INVALID"),
    ],
)
def test_erro_autenticacao_levanta_erro_sem_vazar_chave(
    status_code: int, mensagem: str
) -> None:
    chave = "segredo-google-super-confidencial"
    sdk, _ = _construir_fake_sdk(
        ErroApiGoogleFake(f"{mensagem} {chave}", code=status_code)
    )
    analisador = AnalisadorVisualGoogleAIStudio(chave=chave, genai_sdk=sdk)

    with pytest.raises(ErroAnaliseVisual, match=str(status_code)) as exc_info:
        analisador.analisar(b"png-bytes", 1)

    assert chave not in str(exc_info.value)


def test_erro_transitorio_ou_json_invalido_retorna_lista_vazia() -> None:
    sdk_timeout, reg_timeout = _construir_fake_sdk(TimeoutError("timeout"))
    analisador_timeout = AnalisadorVisualGoogleAIStudio(
        chave="k",
        genai_sdk=sdk_timeout,
        modelos_fallback=(),
        max_tentativas=2,
        sleep_fn=lambda _s: None,
    )
    assert analisador_timeout.analisar(b"png-bytes", 1) == []
    assert reg_timeout["chamadas"] == ["gemma-4-31b-it", "gemma-4-31b-it"]

    sdk_json_ruim, _ = _construir_fake_sdk(_resposta_sdk_fake("não é json"))
    analisador_json_ruim = AnalisadorVisualGoogleAIStudio(chave="k", genai_sdk=sdk_json_ruim)
    assert analisador_json_ruim.analisar(b"png-bytes", 1) == []


def test_retry_bem_sucedido_apos_503_unavailable() -> None:
    erro_503 = ErroApiGoogleFake(
        "This model is currently experiencing high demand.",
        code=503,
        status="UNAVAILABLE",
    )
    resposta_ok = _resposta_sdk_fake(
        '{"tipo": "conteudo", "units": [{"type": "figure", "text": "Slide recuperado."}]}'
    )
    sdk, registro = _construir_fake_sdk([erro_503, resposta_ok])
    pausas: list[float] = []
    analisador = AnalisadorVisualGoogleAIStudio(
        chave="k",
        genai_sdk=sdk,
        modelos_fallback=("gemma-4-26b-a4b-it",),
        max_tentativas=3,
        backoff_inicial_segundos=1.5,
        intervalo_entre_requisicoes_segundos=0.0,
        sleep_fn=pausas.append,
    )

    resultado = analisador.analisar(b"png-bytes", 7)

    assert registro["chamadas"] == ["gemma-4-31b-it", "gemma-4-31b-it"]
    assert len(pausas) == 1
    assert pausas[0] >= 1.5
    assert resultado == [
        {
            "type": "figure",
            "text": "Slide recuperado.",
            "image_classification": "conteudo",
        }
    ]


def test_fallback_automatico_para_modelo_secundario_apos_esgotar_503() -> None:
    erro_503 = ErroApiGoogleFake("High demand", code=503, status="UNAVAILABLE")
    resposta_fallback = _resposta_sdk_fake(
        '{"tipo": "conteudo", "units": [{"type": "table", "text": "Tabela via fallback."}]}'
    )
    sdk, registro = _construir_fake_sdk([erro_503, erro_503, resposta_fallback])
    analisador = AnalisadorVisualGoogleAIStudio(
        chave="k",
        genai_sdk=sdk,
        modelos_fallback=("gemma-4-26b-a4b-it", "gemini-2.5-flash-lite"),
        max_tentativas=2,
        backoff_inicial_segundos=0.5,
        intervalo_entre_requisicoes_segundos=0.0,
        sleep_fn=lambda _s: None,
    )

    resultado = analisador.analisar(b"png-bytes", 7)

    assert registro["chamadas"] == [
        "gemma-4-31b-it",
        "gemma-4-31b-it",
        "gemma-4-26b-a4b-it",
    ]
    assert resultado == [
        {
            "type": "table",
            "text": "Tabela via fallback.",
            "image_classification": "conteudo",
            "model": "gemma-4-26b-a4b-it",
        }
    ]


def test_pula_imediato_para_fallback_em_404_not_found() -> None:
    erro_404 = ErroApiGoogleFake("Model not found", code=404, status="NOT_FOUND")
    resposta_ok = _resposta_sdk_fake(
        '{"tipo": "conteudo", "units": [{"type": "figure", "text": "Ok."}]}'
    )
    sdk, registro = _construir_fake_sdk([erro_404, resposta_ok])
    analisador = AnalisadorVisualGoogleAIStudio(
        chave="k",
        genai_sdk=sdk,
        modelos_fallback=("gemini-2.5-flash-lite",),
        max_tentativas=3,
        intervalo_entre_requisicoes_segundos=0.0,
        sleep_fn=lambda _s: None,
    )

    resultado = analisador.analisar(b"png-bytes", 1)

    assert registro["chamadas"] == ["gemma-4-31b-it", "gemini-2.5-flash-lite"]
    assert resultado[0]["model"] == "gemini-2.5-flash-lite"


def test_pacing_entre_chamadas_consecutivas() -> None:
    resposta = _resposta_sdk_fake(
        '{"tipo": "conteudo", "units": [{"type": "figure", "text": "Slide."}]}'
    )
    sdk, _ = _construir_fake_sdk([resposta, resposta])
    tempo = [10.0]
    pausas: list[float] = []

    def fake_clock() -> float:
        return tempo[0]

    def fake_sleep(segundos: float) -> None:
        pausas.append(round(segundos, 3))
        tempo[0] += segundos

    analisador = AnalisadorVisualGoogleAIStudio(
        chave="k",
        genai_sdk=sdk,
        intervalo_entre_requisicoes_segundos=0.5,
        sleep_fn=fake_sleep,
        clock_fn=fake_clock,
    )

    analisador.analisar(b"png-1", 1)
    tempo[0] += 0.1  # apenas 0.1s depois da primeira chamada
    analisador.analisar(b"png-2", 2)

    assert pausas == [0.4]


def test_limita_concorrencia_maxima_com_semaforo() -> None:
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    lock = threading.Lock()
    ativas = 0
    pico_concorrencia = 0

    class FakeModelsConcorrente:
        def generate_content(
            self, *, model: str, contents: list[object], config: object
        ) -> object:
            nonlocal ativas, pico_concorrencia
            with lock:
                ativas += 1
                pico_concorrencia = max(pico_concorrencia, ativas)
            time.sleep(0.03)
            with lock:
                ativas -= 1
            return _resposta_sdk_fake(
                '{"tipo": "conteudo", "units": [{"type": "figure", "text": "Ok."}]}'
            )

    cliente_fake = SimpleNamespace(models=FakeModelsConcorrente())
    analisador = AnalisadorVisualGoogleAIStudio(
        chave="k",
        cliente=cliente_fake,
        max_concorrencia=2,
        intervalo_entre_requisicoes_segundos=0.0,
    )

    with ThreadPoolExecutor(max_workers=6) as pool:
        resultados = list(pool.map(lambda p: analisador.analisar(b"png", p), range(1, 7)))

    assert len(resultados) == 6
    assert pico_concorrencia <= 2


def test_valida_imagem_vazia_e_chave_ausente() -> None:
    analisador_sem_chave = AnalisadorVisualGoogleAIStudio(chave="")
    with pytest.raises(ErroAnaliseVisual, match="ANOTAI_GOOGLE_API_KEY"):
        analisador_sem_chave.analisar(b"png-bytes", 1)

    analisador_com_chave = AnalisadorVisualGoogleAIStudio(chave="k")
    with pytest.raises(ErroAnaliseVisual, match="vazia"):
        analisador_com_chave.analisar(b"", 1)
