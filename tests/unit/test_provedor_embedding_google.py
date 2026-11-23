from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from anotai.adapters.outbound.google.provedor_embedding import ProvedorEmbeddingGoogleAIStudio
from anotai.adapters.outbound.search.indice_embeddings import IndiceEmbeddings
from anotai.bootstrap import construir_indices_busca, criar_provedor_embedding
from anotai.config import Settings
from anotai.domain.exceptions import ErroBusca


class _ErroHttpFake(Exception):
    def __init__(self, message: str, *, code: int | None = None, status: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


class _ClienteGenAIEmbeddingFake:
    def __init__(self, handler: Any) -> None:
        self.chamadas: list[dict[str, Any]] = []
        self._handler = handler
        self.models = SimpleNamespace(embed_content=self._embed_content)

    def _embed_content(self, **kwargs: Any) -> Any:
        self.chamadas.append(kwargs)
        return self._handler(kwargs)


def test_gerar_embeddings_em_lote_com_cache_e_deduplicacao() -> None:
    def handler(kwargs: dict[str, Any]) -> Any:
        textos = kwargs["contents"]
        return SimpleNamespace(
            embeddings=[
                SimpleNamespace(values=[float(i + 1), float(len(t))])
                for i, t in enumerate(textos)
            ]
        )

    cliente = _ClienteGenAIEmbeddingFake(handler)
    provedor = ProvedorEmbeddingGoogleAIStudio(
        chave="segredo-google",
        modelo="gemini-embedding-001",
        tamanho_lote=2,
        intervalo_entre_requisicoes_segundos=0.0,
        cliente=cliente,
    )

    assert provedor.gerar_embeddings([]) == []
    assert len(cliente.chamadas) == 0

    vetores = provedor.gerar_embeddings(["Alfa", "Beta", "Alfa", "Gama"])
    assert vetores == [[1.0, 4.0], [2.0, 4.0], [1.0, 4.0], [1.0, 4.0]]
    # 3 textos únicos em lotes de tamanho 2 -> 2 chamadas
    assert len(cliente.chamadas) == 2
    assert cliente.chamadas[0]["contents"] == ["Alfa", "Beta"]
    assert cliente.chamadas[1]["contents"] == ["Gama"]

    # Nova chamada com textos já em cache não deve chamar a API
    vetores_cache = provedor.gerar_embeddings(["Beta", "Alfa"])
    assert vetores_cache == [[2.0, 4.0], [1.0, 4.0]]
    assert len(cliente.chamadas) == 2


def test_gerar_embeddings_passa_dimensoes_saida_e_trata_vazios() -> None:
    def handler(kwargs: dict[str, Any]) -> Any:
        textos = kwargs["contents"]
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[1.0, 0.5, 0.25]) for _ in textos]
        )

    cliente = _ClienteGenAIEmbeddingFake(handler)
    provedor = ProvedorEmbeddingGoogleAIStudio(
        chave="segredo-google",
        modelo="gemini-embedding-001",
        dimensoes_saida=3,
        tipo_tarefa="RETRIEVAL_DOCUMENT",
        intervalo_entre_requisicoes_segundos=0.0,
        cliente=cliente,
    )

    vetores = provedor.gerar_embeddings(["Conteúdo válido", "   ", ""])
    assert len(vetores) == 3
    assert vetores[0] == [1.0, 0.5, 0.25]
    assert vetores[1] == [0.0, 0.0, 0.0]
    assert vetores[2] == [0.0, 0.0, 0.0]

    assert len(cliente.chamadas) == 1
    assert cliente.chamadas[0]["contents"] == ["Conteúdo válido"]
    config = cliente.chamadas[0]["config"]
    output_dim = getattr(config, "output_dimensionality", None)
    if output_dim is None and isinstance(config, dict):
        output_dim = config.get("output_dimensionality")
    assert output_dim == 3


def test_retry_em_erro_transitorio_e_falha_imediata_em_auth_sanitizada() -> None:
    tentativas = {"n": 0}
    sleeps: list[float] = []

    def handler_transitorio(kwargs: dict[str, Any]) -> Any:
        tentativas["n"] += 1
        if tentativas["n"] < 3:
            raise _ErroHttpFake("429 RESOURCE_EXHAUSTED", code=429, status="RESOURCE_EXHAUSTED")
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1, 0.9])])

    provedor = ProvedorEmbeddingGoogleAIStudio(
        chave="chave-secreta-123",
        max_tentativas=3,
        backoff_inicial_segundos=1.0,
        intervalo_entre_requisicoes_segundos=0.0,
        sleep_fn=sleeps.append,
        cliente=_ClienteGenAIEmbeddingFake(handler_transitorio),
    )
    vetores = provedor.gerar_embeddings(["teste"])
    assert vetores == [[0.1, 0.9]]
    assert tentativas["n"] == 3
    assert len(sleeps) == 2

    def handler_auth(kwargs: dict[str, Any]) -> Any:
        raise _ErroHttpFake("API key not valid: chave-secreta-123", code=403)

    cliente_auth = _ClienteGenAIEmbeddingFake(handler_auth)
    provedor_auth = ProvedorEmbeddingGoogleAIStudio(
        chave="chave-secreta-123",
        max_tentativas=3,
        intervalo_entre_requisicoes_segundos=0.0,
        cliente=cliente_auth,
    )
    with pytest.raises(ErroBusca, match="HTTP 403") as exc_info:
        provedor_auth.gerar_embeddings(["teste"])
    assert "chave-secreta-123" not in str(exc_info.value)
    assert len(cliente_auth.chamadas) == 1


def test_erro_resposta_vazia_ou_divergente() -> None:
    cliente_vazio = _ClienteGenAIEmbeddingFake(lambda _kw: SimpleNamespace(embeddings=[]))
    provedor_vazio = ProvedorEmbeddingGoogleAIStudio(
        chave="k",
        intervalo_entre_requisicoes_segundos=0.0,
        cliente=cliente_vazio,
    )
    with pytest.raises(ErroBusca, match="não conteve embeddings"):
        provedor_vazio.gerar_embeddings(["um"])

    cliente_div = _ClienteGenAIEmbeddingFake(
        lambda _kw: SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0])])
    )
    provedor_div = ProvedorEmbeddingGoogleAIStudio(
        chave="k",
        intervalo_entre_requisicoes_segundos=0.0,
        cliente=cliente_div,
    )
    with pytest.raises(ErroBusca, match="Quantidade de vetores retornada"):
        provedor_div.gerar_embeddings(["um", "dois"])


def test_integracao_indice_embeddings_com_google_ai_studio() -> None:
    mapa = {
        "gradiente descendente": [1.0, 0.0],
        "árvore de decisão": [0.0, 1.0],
        "otimização por gradiente": [0.95, 0.05],
    }

    def handler(kwargs: dict[str, Any]) -> Any:
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=mapa[t]) for t in kwargs["contents"]]
        )

    provedor = ProvedorEmbeddingGoogleAIStudio(
        chave="k",
        intervalo_entre_requisicoes_segundos=0.0,
        cliente=_ClienteGenAIEmbeddingFake(handler),
    )
    indice = IndiceEmbeddings(provedor)
    indice.indexar([("p1", "gradiente descendente"), ("p2", "árvore de decisão")])

    res = indice.consultar_lote(["otimização por gradiente"], top_k=1)
    assert res[0][0][0] == "p1"
    assert res[0][0][1] > 0.9


def test_bootstrap_embedding_google_ai_studio() -> None:
    cfg_sem_chave = Settings(embedding_provider="google_ai_studio", google_api_key="")
    with pytest.raises(ErroBusca, match="ANOTAI_GOOGLE_API_KEY"):
        criar_provedor_embedding(cfg_sem_chave)

    cfg_invalido = Settings(embedding_provider="desconhecido")
    with pytest.raises(ErroBusca, match="não suportado"):
        criar_provedor_embedding(cfg_invalido)

    cfg_ok = Settings(
        embedding_provider="google_ai_studio",
        google_api_key="chave-teste",
        google_embedding_model="gemini-embedding-001",
        google_embedding_dimensions=768,
    )
    idx_pag, idx_uni = construir_indices_busca("embedding", cfg_ok)
    assert isinstance(idx_pag, IndiceEmbeddings)
    assert isinstance(idx_uni, IndiceEmbeddings)
    assert isinstance(idx_pag.provedor, ProvedorEmbeddingGoogleAIStudio)
    assert idx_pag.provedor.modelo == "gemini-embedding-001"
    assert idx_pag.provedor.dimensoes_saida == 768
