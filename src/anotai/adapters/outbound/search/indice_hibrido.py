from collections.abc import Sequence

from anotai.application.ports.indice_busca import IndiceBusca


class IndiceHibrido(IndiceBusca):
    """Adaptador de busca híbrida combinando sinais lexicais (BM25) e semânticos (Embeddings)."""

    def __init__(
        self,
        indice_lexico: IndiceBusca,
        indice_semantico: IndiceBusca,
        peso_semantica: float = 0.5,
    ) -> None:
        self.indice_lexico = indice_lexico
        self.indice_semantico = indice_semantico
        self.peso_semantica = max(0.0, min(1.0, peso_semantica))

    def indexar(self, itens: Sequence[tuple[str, str]]) -> None:
        self.indice_lexico.indexar(itens)
        self.indice_semantico.indexar(itens)

    def consultar_lote(
        self, consultas: Sequence[str], top_k: int = 5
    ) -> list[list[tuple[str, float]]]:
        if not consultas:
            return []

        # Amostra um conjunto maior de candidatos de cada fonte para fusão robusta
        k_candidatos = max(top_k * 3, 15)
        res_lexico = self.indice_lexico.consultar_lote(consultas, top_k=k_candidatos)
        res_semantico = self.indice_semantico.consultar_lote(consultas, top_k=k_candidatos)

        peso_sem = self.peso_semantica
        peso_lex = 1.0 - peso_sem

        resultados: list[list[tuple[str, float]]] = []
        for i in range(len(consultas)):
            mapa_lex = dict(res_lexico[i]) if i < len(res_lexico) else {}
            mapa_sem = dict(res_semantico[i]) if i < len(res_semantico) else {}

            todos_ids = set(mapa_lex.keys()) | set(mapa_sem.keys())
            candidatos_pontuados: list[tuple[str, float]] = []

            for item_id in todos_ids:
                s_lex = mapa_lex.get(item_id, 0.0)
                s_sem = mapa_sem.get(item_id, 0.0)
                score_hibrido = round(peso_lex * s_lex + peso_sem * s_sem, 4)
                if score_hibrido > 0.0:
                    candidatos_pontuados.append((item_id, score_hibrido))

            # Ordena por pontuação decrescente
            candidatos_pontuados.sort(key=lambda x: x[1], reverse=True)
            resultados.append(candidatos_pontuados[:top_k])

        return resultados
