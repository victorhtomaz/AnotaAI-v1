import pytest

from anotai.adapters.outbound.ollama import AnalisadorVisualOllama
from anotai.domain.entities import UnidadeDocumento
from anotai.domain.exceptions import ErroAnaliseVisual


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.chat_kwargs = None

    def chat(self, **kwargs):
        self.chat_kwargs = kwargs
        return self.response

    def show(self, **kwargs):
        return self.response


def test_default_prompt_uses_document_unit_contract() -> None:
    prompt = AnalisadorVisualOllama(FakeClient({})).prompt

    assert '"units"' in prompt
    assert '"type"' in prompt
    assert '"text"' in prompt
    assert '"bbox"' not in prompt
    assert '"tipo"' in prompt
    assert "decorativo" in prompt
    for tipo in UnidadeDocumento.TIPOS_VISUAIS_VALIDOS:
        assert tipo in prompt
    for tipo in UnidadeDocumento.TIPOS_VALIDOS - UnidadeDocumento.TIPOS_VISUAIS_VALIDOS:
        assert tipo not in prompt


def test_validates_structured_ollama_response() -> None:
    cliente = FakeClient(
        {"message": {"content": '{"units": [{"type": "figure", "text": "Título"}]}'}}
    )
    analyzer = AnalisadorVisualOllama(
        cliente,
        prompt="prompt de teste",
        temperatura=0.0,
        seed=42,
        pensar=False,
        manter_vivo="10m",
    )

    assert analyzer.analisar(b"png", 1)[0]["text"] == "Título"
    assert cliente.chat_kwargs["model"] == "qwen3-vl:8b"
    assert cliente.chat_kwargs["messages"][0]["content"] == "prompt de teste"
    assert cliente.chat_kwargs["messages"][0]["images"] == [b"png"]
    assert cliente.chat_kwargs["format"] == "json"
    assert cliente.chat_kwargs["options"] == {"temperature": 0.0, "seed": 42}
    assert cliente.chat_kwargs["think"] is False
    assert cliente.chat_kwargs["keep_alive"] == "10m"


def test_rejects_invalid_ollama_response() -> None:
    analyzer = AnalisadorVisualOllama(FakeClient({"message": {"content": "not-json"}}))

    assert analyzer.analisar(b"png", 1) == []


@pytest.mark.parametrize(
    "conteudo",
    [
        '```json\n{"units": [{"type": "figure", "text": "Título"}]}\n```',
        'Aqui está o resultado:\n{"units": [{"type": "figure", "text": "Título"}]}',
    ],
)
def test_accepts_json_embedded_in_model_response(conteudo: str) -> None:
    analyzer = AnalisadorVisualOllama(FakeClient({"message": {"content": conteudo}}))

    assert analyzer.analisar(b"png", 1)[0]["text"] == "Título"


def test_accepts_response_field_from_ollama() -> None:
    analyzer = AnalisadorVisualOllama(
        FakeClient({"response": '{"units": [{"type": "figure", "text": "Imagem"}]}'}),
    )

    assert analyzer.analisar(b"png", 1)[0]["text"] == "Imagem"


def test_propagates_visual_classification() -> None:
    analyzer = AnalisadorVisualOllama(
        FakeClient(
            {
                "message": {
                    "content": ('{"tipo":"decorativo","units":[{"type":"figure","text":null}]}')
                }
            }
        )
    )

    assert analyzer.analisar(b"png", 1)[0]["image_classification"] == "decorativo"


def test_preserves_decorative_classification_when_units_empty() -> None:
    analyzer = AnalisadorVisualOllama(
        FakeClient({"message": {"content": '{"tipo":"decorativo","units":[]}'}})
    )

    resultado = analyzer.analisar(b"png", 1)
    assert len(resultado) == 1
    assert resultado[0]["image_classification"] == "decorativo"
    assert resultado[0]["text"] is None


def test_rejects_non_visual_unit_type() -> None:
    analyzer = AnalisadorVisualOllama(
        FakeClient({"message": {"content": '{"units":[{"type":"paragraph","text":"texto"}]}'}})
    )

    assert analyzer.analisar(b"png", 1) == []


def test_keeps_valid_visual_units_when_mixed_with_invalid_type() -> None:
    analyzer = AnalisadorVisualOllama(
        FakeClient(
            {
                "message": {
                    "content": (
                        '{"units":['
                        '{"type":"paragraph","text":"ignorar"},'
                        '{"type":"figure","text":"Diagrama de blocos"}'
                        "]}"
                    )
                }
            }
        )
    )

    resultado = analyzer.analisar(b"png", 1)
    assert len(resultado) == 1
    assert resultado[0]["type"] == "figure"
    assert resultado[0]["text"] == "Diagrama de blocos"


def test_rejects_empty_ollama_response() -> None:
    analyzer = AnalisadorVisualOllama(FakeClient({"response": ""}))

    assert analyzer.analisar(b"png", 1) == []


def test_continues_when_ollama_request_fails() -> None:
    class FailingClient(FakeClient):
        def chat(self, **kwargs):
            raise TimeoutError("Ollama indisponível")

    analyzer = AnalisadorVisualOllama(FailingClient({}))

    assert analyzer.analisar(b"png", 1) == []


def test_rejects_model_without_visual_capability() -> None:
    analyzer = AnalisadorVisualOllama(FakeClient({"details": {"families": ["llama"]}}))

    with pytest.raises(ErroAnaliseVisual, match="capacidade visual"):
        analyzer.validar_modelo_visual()


def test_accepts_model_with_visual_capability() -> None:
    analyzer = AnalisadorVisualOllama(FakeClient({"capabilities": ["vision"]}))

    analyzer.validar_modelo_visual()


def test_combines_ocr_text_and_description_fields() -> None:
    analyzer = AnalisadorVisualOllama(
        FakeClient(
            {
                "message": {
                    "content": (
                        '{"tipo":"conteudo","texto_ocr":"Eixo X: Tempo",'
                        '"descricao":"Gráfico de evolução temporal"}'
                    )
                }
            }
        )
    )

    resultado = analyzer.analisar(b"png", 1)
    assert len(resultado) == 1
    assert resultado[0]["type"] == "figure"
    assert resultado[0]["text"] == "Eixo X: Tempo - Gráfico de evolução temporal"


@pytest.mark.parametrize(
    ("tipo_bruto", "tipo_esperado"),
    [
        ("diagram", "figure"),
        ("imagem", "figure"),
        ("fluxograma", "figure"),
        ("chart", "graph"),
        ("gráfico", "graph"),
        ("tabela", "table"),
        ("equation", "formula"),
    ],
)
def test_normalizes_equivalent_visual_unit_types(tipo_bruto: str, tipo_esperado: str) -> None:
    analyzer = AnalisadorVisualOllama(
        FakeClient(
            {
                "message": {
                    "content": (
                        f'{{"tipo":"conteúdo","units":[{{"type":"{tipo_bruto}",'
                        '"description":"Ilustração sem texto interno"}}]}'
                    )
                }
            }
        )
    )

    resultado = analyzer.analisar(b"png", 1)
    assert len(resultado) == 1
    assert resultado[0]["type"] == tipo_esperado
    assert resultado[0]["image_classification"] == "conteudo"
    assert resultado[0]["text"] == "Ilustração sem texto interno"
