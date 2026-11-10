from collections.abc import Sequence

import bm25s

from anotai.application.ports.indice_busca import IndiceBusca


class IndiceBM25(IndiceBusca):
    """Adaptador de busca lexical baseado na biblioteca bm25s com suporte a português."""

    def __init__(self, k_saturacao: float = 2.0) -> None:
        self.k_saturacao = k_saturacao
        self._ids: list[str] = []
        self._retriever: bm25s.BM25 | None = None

    def indexar(self, itens: Sequence[tuple[str, str]]) -> None:
        self._ids = [item[0] for item in itens]
        textos = [item[1] for item in itens]

        if not self._ids or not any(t.strip() for t in textos):
            self._retriever = None
            return

        corpus_tokens = bm25s.tokenize(
            textos,
            stopwords="pt",
            token_pattern=r"(?u)\b\w+\b",
            show_progress=False,
        )
        retriever = bm25s.BM25()
        retriever.index(corpus_tokens, show_progress=False)
        self._retriever = retriever

    def consultar_lote(
        self, consultas: Sequence[str], top_k: int = 5
    ) -> list[list[tuple[str, float]]]:
        if not consultas:
            return []

        if not self._ids or self._retriever is None or top_k <= 0:
            return [[] for _ in consultas]

        consultas_lista = [str(c) for c in consultas]
        tokens_consultas = bm25s.tokenize(
            consultas_lista,
            stopwords="pt",
            token_pattern=r"(?u)\b\w+\b",
            show_progress=False,
        )

        k_efetivo = min(top_k, len(self._ids))
        if k_efetivo <= 0:
            return [[] for _ in consultas]

        docs, scores = self._retriever.retrieve(tokens_consultas, k=k_efetivo, show_progress=False)

        # Garante formato 2D mesmo em casos limites
        if getattr(docs, "ndim", 2) == 1:
            docs = docs.reshape(len(consultas_lista), -1)
            scores = scores.reshape(len(consultas_lista), -1)

        resultados: list[list[tuple[str, float]]] = []
        for i in range(len(consultas_lista)):
            linha_res: list[tuple[str, float]] = []
            for doc_idx, raw_score in zip(docs[i], scores[i], strict=False):
                pontuacao_bruta = float(raw_score)
                if pontuacao_bruta <= 0.0:
                    continue
                # Normalização monotônica não-linear em [0, 1)
                pontuacao_norm = round(
                    pontuacao_bruta / (pontuacao_bruta + self.k_saturacao),
                    4,
                )
                linha_res.append((self._ids[int(doc_idx)], pontuacao_norm))
            resultados.append(linha_res)

        return resultados
