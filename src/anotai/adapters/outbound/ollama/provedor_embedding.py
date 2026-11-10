from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ollama import ResponseError

from anotai.domain.exceptions.ErroBusca import ErroBusca


class ClienteOllamaEmbed(Protocol):
    def embed(self, **kwargs: Any) -> Any: ...


@dataclass
class ProvedorEmbeddingOllama:
    cliente: ClienteOllamaEmbed
    modelo: str = "bge-m3:567m"
    manter_vivo: str | int | float = "5m"

    def gerar_embeddings(self, textos: Sequence[str]) -> list[list[float]]:
        if not textos:
            return []

        lista_textos = [str(t) for t in textos]
        try:
            resposta = self.cliente.embed(
                model=self.modelo,
                input=lista_textos,
                keep_alive=self.manter_vivo,
            )
        except (OSError, ResponseError, TimeoutError, Exception) as exc:
            raise ErroBusca(
                f"Falha ao gerar embeddings via Ollama com modelo '{self.modelo}': {exc}"
            ) from exc

        if hasattr(resposta, "embeddings"):
            vetores = resposta.embeddings
        elif isinstance(resposta, dict):
            vetores = resposta.get("embeddings")
        else:
            vetores = getattr(resposta, "embedding", None)

        if vetores is None:
            raise ErroBusca(
                f"Resposta do Ollama não conteve embeddings para o modelo '{self.modelo}'"
            )

        if not isinstance(vetores, list):
            vetores = list(vetores)

        # Se for um único vetor 1D por engano, encapsula em lista 2D
        if vetores and isinstance(vetores[0], (int, float)):
            vetores = [vetores]

        resultado: list[list[float]] = []
        for v in vetores:
            if not isinstance(v, list):
                v = list(v)
            resultado.append([float(x) for x in v])

        if len(resultado) != len(lista_textos):
            raise ErroBusca(
                f"Quantidade de vetores retornada ({len(resultado)}) difere da "
                f"quantidade de textos enviada ({len(lista_textos)})"
            )

        return resultado
