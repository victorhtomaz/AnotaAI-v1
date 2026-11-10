from collections.abc import Sequence

import numpy as np

from anotai.application.ports.indice_busca import IndiceBusca
from anotai.application.ports.provedor_embedding import ProvedorEmbedding


class IndiceEmbeddings(IndiceBusca):
    """Adaptador de busca semântica por similaridade de cosseno via embeddings vetoriais."""

    def __init__(self, provedor: ProvedorEmbedding) -> None:
        self.provedor = provedor
        self._ids: list[str] = []
        self._matriz: np.ndarray | None = None

    def indexar(self, itens: Sequence[tuple[str, str]]) -> None:
        self._ids = [item[0] for item in itens]
        textos = [item[1] for item in itens]

        if not self._ids or not any(t.strip() for t in textos):
            self._matriz = None
            return

        vetores = self.provedor.gerar_embeddings(textos)
        matriz = np.array(vetores, dtype=np.float32)

        normas = np.linalg.norm(matriz, axis=1, keepdims=True)
        normas[normas == 0.0] = 1.0
        self._matriz = matriz / normas

    def consultar_lote(
        self, consultas: Sequence[str], top_k: int = 5
    ) -> list[list[tuple[str, float]]]:
        if not consultas:
            return []

        if not self._ids or self._matriz is None or top_k <= 0:
            return [[] for _ in consultas]

        vetores_consultas = self.provedor.gerar_embeddings(list(consultas))
        matriz_q = np.array(vetores_consultas, dtype=np.float32)

        normas_q = np.linalg.norm(matriz_q, axis=1, keepdims=True)
        normas_q[normas_q == 0.0] = 1.0
        matriz_q = matriz_q / normas_q

        # Produto escalar de vetores L2 normalizados = similaridade de cosseno
        sims = matriz_q @ self._matriz.T

        k_efetivo = min(top_k, len(self._ids))
        resultados: list[list[tuple[str, float]]] = []

        for i in range(len(consultas)):
            linha_sim = sims[i]
            # Ordenação decrescente de similaridade
            indices_ordenados = np.argsort(-linha_sim)
            linha_res: list[tuple[str, float]] = []
            for idx in indices_ordenados[:k_efetivo]:
                val = float(linha_sim[idx])
                if val <= 0.0:
                    continue
                score_norm = round(min(1.0, max(0.0, val)), 4)
                linha_res.append((self._ids[idx], score_norm))
            resultados.append(linha_res)

        return resultados
