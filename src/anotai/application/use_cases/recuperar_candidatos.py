from anotai.application.ports.indice_busca import IndiceBusca
from anotai.domain.entities import Aula, Documento
from anotai.domain.value_objects import (
    CandidatoPagina,
    CandidatoUnidade,
    ResultadoRecuperacaoIntervalo,
    agregar_pontuacao_unidades,
    combinar_pontuacao_pagina,
)


class RecuperarCandidatos:
    """Caso de uso para recuperação de páginas e unidades a partir de intervalos de fala."""

    def __init__(
        self,
        indice_paginas: IndiceBusca,
        indice_unidades: IndiceBusca,
        estrategia: str = "bm25",
        top_k_paginas: int = 5,
        top_k_unidades: int = 5,
        limiar_abstencao: float = 0.0,
    ) -> None:
        self.indice_paginas = indice_paginas
        self.indice_unidades = indice_unidades
        self.estrategia = estrategia
        self.top_k_paginas = max(1, top_k_paginas)
        self.top_k_unidades = max(1, top_k_unidades)
        self.limiar_abstencao = max(0.0, float(limiar_abstencao))

    def executar(
        self, aula: Aula, documento: Documento
    ) -> list[ResultadoRecuperacaoIntervalo]:
        # 1. Preparação dos itens para indexação
        itens_paginas: list[tuple[str, str]] = [
            (p.id_pagina, p.texto_normalizado or p.texto_nativo)
            for p in documento.paginas
        ]
        self.indice_paginas.indexar(itens_paginas)

        # Unidades decorativas são descartadas do alinhamento conforme regras de negócio
        itens_unidades: list[tuple[str, str]] = []
        mapa_unidades = {}
        for p in documento.paginas:
            for u in p.unidades:
                if u.participa_alinhamento and u.texto and u.texto.strip():
                    itens_unidades.append((u.id_unidade, u.texto))
                    mapa_unidades[u.id_unidade] = (u, p.id_pagina, p.numero_pagina)

        self.indice_unidades.indexar(itens_unidades)

        mapa_paginas = {p.id_pagina: p for p in documento.paginas}

        if not aula.intervalos:
            return []

        consultas = [inter.texto for inter in aula.intervalos]

        # 2. Consultas em lote
        k_paginas_amostra = len(documento.paginas)
        res_paginas = self.indice_paginas.consultar_lote(consultas, top_k=k_paginas_amostra)
        k_unidades_amostra = max(self.top_k_unidades * 3, 10)
        res_unidades = self.indice_unidades.consultar_lote(consultas, top_k=k_unidades_amostra)

        # 3. Consolidação e agregação de evidências por intervalo
        resultados: list[ResultadoRecuperacaoIntervalo] = []

        for idx, inter in enumerate(aula.intervalos):
            # Mapeia candidatos de unidade
            candidatos_unidade_todos: list[CandidatoUnidade] = []
            unidades_por_pagina: dict[str, list[CandidatoUnidade]] = {}

            matches_unidades = res_unidades[idx] if idx < len(res_unidades) else []
            for id_unidade, score_u in matches_unidades:
                if id_unidade in mapa_unidades:
                    u_entidade, id_pag, num_pag = mapa_unidades[id_unidade]
                    cand_u = CandidatoUnidade(
                        id_unidade=u_entidade.id_unidade,
                        id_pagina=id_pag,
                        numero_pagina=num_pag,
                        tipo_unidade=u_entidade.tipo,
                        ordem_leitura=u_entidade.ordem_leitura,
                        texto=u_entidade.texto,
                        pontuacao=score_u,
                        estrategia=self.estrategia,
                        fonte=u_entidade.fonte,
                        ids_evidencias=tuple(u_entidade.ids_evidencias),
                    )
                    candidatos_unidade_todos.append(cand_u)
                    unidades_por_pagina.setdefault(id_pag, []).append(cand_u)

            # Mapeia pontuações diretas de página
            matches_paginas = res_paginas[idx] if idx < len(res_paginas) else []
            scores_diretos_pagina = dict(matches_paginas)

            # Combina evidência de página direta + unidades
            todas_paginas_candidatas = set(scores_diretos_pagina.keys()) | set(
                unidades_por_pagina.keys()
            )
            candidatos_pagina_todos: list[CandidatoPagina] = []

            for id_pag in todas_paginas_candidatas:
                p_entidade = mapa_paginas.get(id_pag)
                if p_entidade is None:
                    continue

                s_direto = scores_diretos_pagina.get(id_pag, 0.0)
                unidades_da_pag = unidades_por_pagina.get(id_pag, [])
                s_unidades = agregar_pontuacao_unidades([u.pontuacao for u in unidades_da_pag])
                s_final = combinar_pontuacao_pagina(s_direto, s_unidades)

                if s_final > 0.0:
                    candidatos_pagina_todos.append(
                        CandidatoPagina(
                            id_pagina=p_entidade.id_pagina,
                            numero_pagina=p_entidade.numero_pagina,
                            texto=p_entidade.texto_normalizado,
                            pontuacao=s_final,
                            pontuacao_direta=s_direto,
                            pontuacao_unidades=s_unidades,
                            estrategia=self.estrategia,
                            unidades_evidencia=tuple(unidades_da_pag),
                        )
                    )

            # Ordena decrescente por relevância
            candidatos_pagina_todos.sort(key=lambda c: c.pontuacao, reverse=True)
            candidatos_unidade_todos.sort(key=lambda c: c.pontuacao, reverse=True)

            candidatos_pagina_final = tuple(candidatos_pagina_todos[: self.top_k_paginas])
            candidatos_unidade_final = tuple(candidatos_unidade_todos[: self.top_k_unidades])

            # Decisão de abstenção
            maior_p = candidatos_pagina_final[0].pontuacao if candidatos_pagina_final else 0.0
            maior_u = candidatos_unidade_final[0].pontuacao if candidatos_unidade_final else 0.0
            maior_pontuacao = max(maior_p, maior_u)

            if maior_pontuacao <= 0.0:
                abstido = True
                motivo = "Nenhuma evidência documental encontrada para o intervalo"
            elif maior_pontuacao < self.limiar_abstencao:
                abstido = True
                motivo = (
                    f"Pontuação máxima ({maior_pontuacao:.4f}) abaixo do limiar "
                    f"de abstenção ({self.limiar_abstencao:.4f})"
                )
            else:
                abstido = False
                motivo = None

            resultados.append(
                ResultadoRecuperacaoIntervalo(
                    id_intervalo=inter.id_intervalo,
                    ordem_intervalo=inter.ordem,
                    texto_intervalo=inter.texto,
                    intervalo_tempo=inter.intervalo,
                    id_documento=documento.id_documento,
                    estrategia=self.estrategia,
                    candidatos_pagina=candidatos_pagina_final,
                    candidatos_unidade=candidatos_unidade_final,
                    abstido=abstido,
                    limiar_abstencao=self.limiar_abstencao,
                    maior_pontuacao=maior_pontuacao,
                    motivo_abstencao=motivo,
                )
            )

        return resultados
