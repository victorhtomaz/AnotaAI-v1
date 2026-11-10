from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from ollama import ResponseError

from anotai.domain.exceptions import ErroBusca


class ClienteOllamaEmbed(Protocol):
    def embed(self, **kwargs: Any) -> Any: ...


@dataclass
class ProvedorEmbeddingOllama:
    cliente: ClienteOllamaEmbed
    modelo: str = "bge-m3:567m"
    manter_vivo: str | int | float = "5m"
    tamanho_lote: int = 32
    _cache: dict[str, list[float]] = field(default_factory=dict, init=False, repr=False)

    def gerar_embeddings(self, textos: Sequence[str]) -> list[list[float]]:
        if not textos:
            return []

        lista_textos = [str(t) for t in textos]
        faltantes = [t for t in lista_textos if t not in self._cache]

        if faltantes:
            if len(faltantes) <= self.tamanho_lote:
                novos_vetores = self._gerar_lote_individual(faltantes)
                for t, v in zip(faltantes, novos_vetores, strict=True):
                    self._cache[t] = v
            else:
                for i in range(0, len(faltantes), self.tamanho_lote):
                    chunk = faltantes[i : i + self.tamanho_lote]
                    novos_vetores = self._gerar_lote_individual(chunk)
                    for t, v in zip(chunk, novos_vetores, strict=True):
                        self._cache[t] = v

        return [self._cache[t] for t in lista_textos]

    def _gerar_lote_individual(self, lista_textos: list[str]) -> list[list[float]]:
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
