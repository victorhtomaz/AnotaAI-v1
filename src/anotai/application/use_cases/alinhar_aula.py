from collections.abc import Sequence

from anotai.application.ports.repositorio_alinhamento import RepositorioAlinhamento
from anotai.application.use_cases.recuperar_candidatos import RecuperarCandidatos
from anotai.domain.entities import Alinhamento, Aula, Documento, ValidadorIntegridade
from anotai.domain.value_objects import (
    CandidatoPagina,
    CandidatoUnidade,
    OrigemAlinhamento,
    ParametrosHMM,
    PesosAlinhamento,
    PontuacaoCandidatoAlinhamento,
    ResultadoAlinhamentoIntervalo,
    ResultadoRecuperacaoIntervalo,
    StatusAlinhamento,
    TipoRelacao,
    calcular_contexto_temporal_pagina,
    calcular_evidencia_visual_pagina,
    calcular_posteriores_hmm,
    combinar_sinais_alinhamento,
)
from anotai.domain.value_objects.evidencia_recuperacao import TIPOS_UNIDADES_VISUAIS


class AlinharAula:
    """Caso de uso da Fase 6 para alinhamento hierárquico e temporal entre aula e PDF."""

    ESTRATEGIAS_SUPORTADAS = {
        "bm25",
        "embedding",
        "hybrid",
        "temporal",
        "temporal_hmm",
        "hierarchical",
        "hierarchical_hmm",
    }
    MODELOS_TEMPORAIS_SUPORTADOS = {"kernel", "hmm"}

    def __init__(
        self,
        recuperador: RecuperarCandidatos,
        repositorio_alinhamento: RepositorioAlinhamento | None = None,
        estrategia: str = "hierarchical",
        modelo_temporal: str = "kernel",
        pesos: PesosAlinhamento | None = None,
        parametros_hmm: ParametrosHMM | None = None,
        limiar_abstencao: float = 0.0,
        max_paginas: int = 3,
        max_unidades: int = 5,
        incluir_unidades: bool = True,
    ) -> None:
        estrategia_norm = estrategia.strip().lower()
        if estrategia_norm not in self.ESTRATEGIAS_SUPORTADAS:
            raise ValueError(
                f"Estratégia de alinhamento inválida: '{estrategia}'. "
                f"Esperado uma de: {', '.join(sorted(self.ESTRATEGIAS_SUPORTADAS))}"
            )

        modelo_norm = modelo_temporal.strip().lower()
        if modelo_norm not in self.MODELOS_TEMPORAIS_SUPORTADOS:
            raise ValueError(
                f"Modelo temporal inválido: '{modelo_temporal}'. Esperado: 'kernel' ou 'hmm'"
            )

        if estrategia_norm in ("temporal_hmm", "hierarchical_hmm"):
            modelo_norm = "hmm"
        elif modelo_norm == "hmm":
            if estrategia_norm == "temporal":
                estrategia_norm = "temporal_hmm"
            elif estrategia_norm == "hierarchical":
                estrategia_norm = "hierarchical_hmm"

        self.recuperador = recuperador
        self.repositorio_alinhamento = repositorio_alinhamento
        self.estrategia = estrategia_norm
        self.modelo_temporal = modelo_norm
        self.pesos = pesos if pesos is not None else PesosAlinhamento()
        self.parametros_hmm = (
            parametros_hmm if parametros_hmm is not None else ParametrosHMM()
        )
        self.limiar_abstencao = max(0.0, min(1.0, float(limiar_abstencao)))
        self.max_paginas = max(1, int(max_paginas))
        self.max_unidades = max(1, int(max_unidades))
        self.incluir_unidades = incluir_unidades

    def executar(
        self,
        aula: Aula,
        documento: Documento,
        resultados_recuperacao: Sequence[ResultadoRecuperacaoIntervalo] | None = None,
    ) -> list[ResultadoAlinhamentoIntervalo]:
        if not aula.intervalos:
            return []

        if resultados_recuperacao is None:
            top_k_pag_original = self.recuperador.top_k_paginas
            try:
                self.recuperador.top_k_paginas = max(
                    top_k_pag_original, len(documento.paginas), 1
                )
                resultados_base = self.recuperador.executar(aula, documento)
            finally:
                self.recuperador.top_k_paginas = top_k_pag_original
        else:
            resultados_base = list(resultados_recuperacao)

        usa_hierarquia = self.estrategia in ("hierarchical", "hierarchical_hmm")
        usa_temporal = self.estrategia in (
            "temporal",
            "temporal_hmm",
            "hierarchical",
            "hierarchical_hmm",
        ) and (self.modelo_temporal == "hmm" or self.pesos.peso_temporal > 0.0)
        usa_hmm = usa_temporal and self.modelo_temporal == "hmm"
        peso_vis_efetivo = (
            max(0.0, self.pesos.peso_visual)
            if (usa_hierarquia or usa_temporal)
            else 0.0
        )

        paginas_ordenadas = sorted(
            [(p.id_pagina, p.numero_pagina) for p in documento.paginas],
            key=lambda x: x[1],
        )
        mapa_num_pagina = dict(paginas_ordenadas)

        posteriores_hmm: list[tuple[dict[str, float], float]] = []
        if usa_hmm:
            posteriores_hmm = calcular_posteriores_hmm(
                resultados_base=resultados_base,
                paginas_ordenadas=paginas_ordenadas,
                params_hmm=self.parametros_hmm,
                peso_visual=peso_vis_efetivo,
            )

        resultados_finais: list[ResultadoAlinhamentoIntervalo] = []
        alinhamentos_para_salvar: list[Alinhamento] = []

        for idx, inter in enumerate(aula.intervalos):
            res_base = resultados_base[idx]
            gamma_paginas: dict[str, float] = {}
            gamma_abstencao: float | None = None
            if usa_hmm and idx < len(posteriores_hmm):
                gamma_paginas, gamma_abstencao = posteriores_hmm[idx]

            avaliacoes_paginas = self._avaliar_paginas_intervalo(
                idx_intervalo=idx,
                res_base=res_base,
                resultados_base=resultados_base,
                mapa_num_pagina=mapa_num_pagina,
                usa_temporal=usa_temporal,
                usa_hmm=usa_hmm,
                peso_vis_efetivo=peso_vis_efetivo,
                gamma_paginas=gamma_paginas,
            )

            maior_sim_bruta = max(
                (c.pontuacao for c in res_base.candidatos_pagina), default=0.0
            )
            melhor_pag_score = (
                avaliacoes_paginas[0].pontuacao_final if avaliacoes_paginas else 0.0
            )

            abstido, motivo_abstencao = self._decidir_abstencao(
                maior_sim_bruta=maior_sim_bruta,
                melhor_pag_score=melhor_pag_score,
                usa_hmm=usa_hmm,
                gamma_abstencao=gamma_abstencao,
            )

            if abstido:
                cands_pag_marcados = tuple(
                    PontuacaoCandidatoAlinhamento(
                        id_item=cp.id_item,
                        numero_pagina=cp.numero_pagina,
                        pontuacao_similaridade=cp.pontuacao_similaridade,
                        pontuacao_temporal=cp.pontuacao_temporal,
                        pontuacao_visual=cp.pontuacao_visual,
                        pontuacao_final=cp.pontuacao_final,
                        selecionado=False,
                    )
                    for cp in avaliacoes_paginas
                )
                alinhamento = Alinhamento(
                    id_alinhamento=Alinhamento.gerar_id_estavel(
                        inter.id_intervalo,
                        documento.id_documento,
                        self.estrategia,
                        OrigemAlinhamento.AUTOMATICO.value,
                    ),
                    id_aula=aula.id_aula,
                    id_documento=documento.id_documento,
                    id_intervalo=inter.id_intervalo,
                    ids_paginas=[],
                    ids_unidades=[],
                    status=StatusAlinhamento.ABSTIDO.value,
                    tipo_relacao=None,
                    confianca=round(melhor_pag_score, 4),
                    estrategia=self.estrategia,
                    ids_evidencias=[],
                    versao_processamento=documento.versao_processamento,
                    justificativa=motivo_abstencao,
                    origem=OrigemAlinhamento.AUTOMATICO.value,
                )
                ValidadorIntegridade.validar_alinhamento(alinhamento, aula, documento)
                alinhamentos_para_salvar.append(alinhamento)
                resultados_finais.append(
                    ResultadoAlinhamentoIntervalo(
                        alinhamento=alinhamento,
                        ordem_intervalo=inter.ordem,
                        texto_intervalo=inter.texto,
                        intervalo_tempo=inter.intervalo,
                        candidatos_pagina=cands_pag_marcados,
                        candidatos_unidade=(),
                        probabilidade_abstencao_hmm=gamma_abstencao,
                    )
                )
                continue

            # Seleção multi-rótulo de páginas
            corte_pag = max(
                self.limiar_abstencao,
                round(melhor_pag_score * self.pesos.fator_multirrotulo, 4),
            )
            ids_paginas_sel: list[str] = []
            cands_pag_finais: list[PontuacaoCandidatoAlinhamento] = []
            mapa_score_pag_sel: dict[str, float] = {}

            for cp in avaliacoes_paginas:
                selecionar = (
                    len(ids_paginas_sel) < self.max_paginas
                    and cp.pontuacao_final >= corte_pag
                    and cp.pontuacao_similaridade > 0.0
                )
                if selecionar:
                    ids_paginas_sel.append(cp.id_item)
                    mapa_score_pag_sel[cp.id_item] = cp.pontuacao_final
                cands_pag_finais.append(
                    PontuacaoCandidatoAlinhamento(
                        id_item=cp.id_item,
                        numero_pagina=cp.numero_pagina,
                        pontuacao_similaridade=cp.pontuacao_similaridade,
                        pontuacao_temporal=cp.pontuacao_temporal,
                        pontuacao_visual=cp.pontuacao_visual,
                        pontuacao_final=cp.pontuacao_final,
                        selecionado=selecionar,
                    )
                )

            # Refinamento / seleção de unidades nas páginas selecionadas
            cands_uni_finais: list[PontuacaoCandidatoAlinhamento] = []
            ids_unidades_sel: list[str] = []
            ids_evidencias: list[str] = list(ids_paginas_sel)

            if self.incluir_unidades and ids_paginas_sel:
                cands_uni_finais, ids_unidades_sel, evidencias_u = (
                    self._refinar_unidades_intervalo(
                        res_base=res_base,
                        ids_paginas_sel=ids_paginas_sel,
                        mapa_score_pag_sel=mapa_score_pag_sel,
                        usa_hierarquia=usa_hierarquia,
                        peso_vis_efetivo=peso_vis_efetivo,
                    )
                )
                ids_evidencias.extend(ids_unidades_sel)
                ids_evidencias.extend(evidencias_u)

            topo_pag = cands_pag_finais[0]
            justificativa = self._formatar_justificativa_alinhamento(
                topo_pag=topo_pag,
                gamma_abstencao=gamma_abstencao,
            )
            tipo_rel = TipoRelacao.normalizar(inter.tipo)

            alinhamento = Alinhamento(
                id_alinhamento=Alinhamento.gerar_id_estavel(
                    inter.id_intervalo,
                    documento.id_documento,
                    self.estrategia,
                    OrigemAlinhamento.AUTOMATICO.value,
                ),
                id_aula=aula.id_aula,
                id_documento=documento.id_documento,
                id_intervalo=inter.id_intervalo,
                ids_paginas=ids_paginas_sel,
                ids_unidades=ids_unidades_sel,
                status=StatusAlinhamento.ALINHADO.value,
                tipo_relacao=tipo_rel.value if tipo_rel else TipoRelacao.DIRETA.value,
                confianca=round(topo_pag.pontuacao_final, 4),
                estrategia=self.estrategia,
                ids_evidencias=ids_evidencias,
                versao_processamento=documento.versao_processamento,
                justificativa=justificativa,
                origem=OrigemAlinhamento.AUTOMATICO.value,
            )
            ValidadorIntegridade.validar_alinhamento(alinhamento, aula, documento)
            alinhamentos_para_salvar.append(alinhamento)

            resultados_finais.append(
                ResultadoAlinhamentoIntervalo(
                    alinhamento=alinhamento,
                    ordem_intervalo=inter.ordem,
                    texto_intervalo=inter.texto,
                    intervalo_tempo=inter.intervalo,
                    candidatos_pagina=tuple(cands_pag_finais),
                    candidatos_unidade=tuple(cands_uni_finais),
                    probabilidade_abstencao_hmm=gamma_abstencao,
                )
            )

        if self.repositorio_alinhamento is not None and alinhamentos_para_salvar:
            self.repositorio_alinhamento.salvar_lote(alinhamentos_para_salvar)

        return resultados_finais

    def registrar_revisao_manual(
        self,
        aula: Aula,
        documento: Documento,
        id_intervalo: str,
        ids_paginas: Sequence[str] = (),
        ids_unidades: Sequence[str] = (),
        abster: bool = False,
        tipo_relacao: str | None = "direct",
        justificativa: str | None = None,
        confianca: float = 1.0,
    ) -> Alinhamento:
        """Registra ou atualiza uma revisão manual de alinhamento distinguindo-a do automático."""
        mapa_unid_pag = {
            u.id_unidade: p.id_pagina for p in documento.paginas for u in p.unidades
        }
        paginas_finais = list(dict.fromkeys(ids_paginas))
        unidades_finais = list(dict.fromkeys(ids_unidades))

        if abster or (not paginas_finais and not unidades_finais):
            status = StatusAlinhamento.ABSTIDO.value
            paginas_finais = []
            unidades_finais = []
            rel_final = None
            just_final = justificativa or "Abstenção definida manualmente na revisão"
        else:
            status = StatusAlinhamento.ALINHADO.value
            for id_u in unidades_finais:
                id_pag_mae = mapa_unid_pag.get(id_u)
                if id_pag_mae and id_pag_mae not in paginas_finais:
                    paginas_finais.append(id_pag_mae)
            rel_norm = TipoRelacao.normalizar(tipo_relacao or "direct")
            rel_final = rel_norm.value if rel_norm else TipoRelacao.DIRETA.value
            just_final = justificativa or "Vínculo revisado manualmente"

        alinhamento = Alinhamento(
            id_alinhamento=Alinhamento.gerar_id_estavel(
                id_intervalo=id_intervalo,
                id_documento=documento.id_documento,
                estrategia="manual",
                origem=OrigemAlinhamento.MANUAL.value,
            ),
            id_aula=aula.id_aula,
            id_documento=documento.id_documento,
            id_intervalo=id_intervalo,
            ids_paginas=paginas_finais,
            ids_unidades=unidades_finais,
            status=status,
            tipo_relacao=rel_final,
            confianca=round(max(0.0, min(1.0, float(confianca))), 4),
            estrategia="manual",
            ids_evidencias=[*paginas_finais, *unidades_finais],
            versao_processamento=documento.versao_processamento,
            justificativa=just_final,
            origem=OrigemAlinhamento.MANUAL.value,
        )

        ValidadorIntegridade.validar_alinhamento(alinhamento, aula, documento)
        if self.repositorio_alinhamento is not None:
            self.repositorio_alinhamento.salvar(alinhamento)

        return alinhamento

    def _avaliar_paginas_intervalo(
        self,
        idx_intervalo: int,
        res_base: ResultadoRecuperacaoIntervalo,
        resultados_base: Sequence[ResultadoRecuperacaoIntervalo],
        mapa_num_pagina: dict[str, int],
        usa_temporal: bool,
        usa_hmm: bool,
        peso_vis_efetivo: float,
        gamma_paginas: dict[str, float],
    ) -> list[PontuacaoCandidatoAlinhamento]:
        avaliacoes: list[PontuacaoCandidatoAlinhamento] = []

        if usa_hmm:
            mapa_cand = {c.id_pagina: c for c in res_base.candidatos_pagina}
            for id_pag, num_pag in mapa_num_pagina.items():
                cand = mapa_cand.get(id_pag)
                s_sim = cand.pontuacao if cand is not None else 0.0
                s_vis = (
                    calcular_evidencia_visual_pagina(cand)
                    if (cand is not None and peso_vis_efetivo > 0.0)
                    else 0.0
                )
                s_gamma = gamma_paginas.get(id_pag, 0.0)
                if s_sim > 0.0 or s_gamma > 0.0:
                    # Nas estratégias *_hmm, gamma já integra emissão e transição:
                    # não soma similaridade uma segunda vez.
                    avaliacoes.append(
                        PontuacaoCandidatoAlinhamento(
                            id_item=id_pag,
                            numero_pagina=num_pag,
                            pontuacao_similaridade=s_sim,
                            pontuacao_temporal=s_gamma,
                            pontuacao_visual=s_vis,
                            pontuacao_final=s_gamma,
                            selecionado=False,
                        )
                    )
        else:
            pesos_efetivos = PesosAlinhamento(
                peso_similaridade=self.pesos.peso_similaridade,
                peso_temporal=self.pesos.peso_temporal if usa_temporal else 0.0,
                peso_visual=peso_vis_efetivo,
                janela_temporal=self.pesos.janela_temporal,
                fator_multirrotulo=self.pesos.fator_multirrotulo,
            )
            for cand in res_base.candidatos_pagina:
                s_sim = cand.pontuacao
                s_temp = (
                    calcular_contexto_temporal_pagina(
                        idx_atual=idx_intervalo,
                        resultados_base=resultados_base,
                        id_pagina=cand.id_pagina,
                        mapa_num_pagina=mapa_num_pagina,
                        janela=self.pesos.janela_temporal,
                    )
                    if usa_temporal
                    else 0.0
                )
                s_vis = (
                    calcular_evidencia_visual_pagina(cand)
                    if peso_vis_efetivo > 0.0
                    else 0.0
                )
                s_final = combinar_sinais_alinhamento(
                    similaridade=s_sim,
                    temporal=s_temp,
                    visual=s_vis,
                    pesos=pesos_efetivos,
                )
                avaliacoes.append(
                    PontuacaoCandidatoAlinhamento(
                        id_item=cand.id_pagina,
                        numero_pagina=cand.numero_pagina,
                        pontuacao_similaridade=s_sim,
                        pontuacao_temporal=s_temp,
                        pontuacao_visual=s_vis,
                        pontuacao_final=s_final,
                        selecionado=False,
                    )
                )

        avaliacoes.sort(
            key=lambda c: (c.pontuacao_final, c.pontuacao_similaridade),
            reverse=True,
        )
        return avaliacoes

    def _decidir_abstencao(
        self,
        maior_sim_bruta: float,
        melhor_pag_score: float,
        usa_hmm: bool,
        gamma_abstencao: float | None,
    ) -> tuple[bool, str | None]:
        if maior_sim_bruta <= 0.0 or melhor_pag_score <= 0.0:
            return True, "Nenhuma evidência documental encontrada para o intervalo"

        if usa_hmm and gamma_abstencao is not None and gamma_abstencao >= melhor_pag_score:
            return (
                True,
                f"Estado de abstenção HMM dominante (gamma_abs={gamma_abstencao:.4f} >= "
                f"max_gamma_pag={melhor_pag_score:.4f})",
            )

        if melhor_pag_score < self.limiar_abstencao:
            return (
                True,
                f"Pontuação máxima de alinhamento ({melhor_pag_score:.4f}) abaixo do limiar "
                f"de abstenção ({self.limiar_abstencao:.4f})",
            )

        return False, None

    def _refinar_unidades_intervalo(
        self,
        res_base: ResultadoRecuperacaoIntervalo,
        ids_paginas_sel: Sequence[str],
        mapa_score_pag_sel: dict[str, float],
        usa_hierarquia: bool,
        peso_vis_efetivo: float,
    ) -> tuple[list[PontuacaoCandidatoAlinhamento], list[str], list[str]]:
        conjunto_pags = set(ids_paginas_sel)
        unidades_candidatas: dict[str, CandidatoUnidade] = {}

        if usa_hierarquia:
            mapa_pag_cand: dict[str, CandidatoPagina] = {
                cp.id_pagina: cp for cp in res_base.candidatos_pagina
            }
            for id_pag in ids_paginas_sel:
                cp = mapa_pag_cand.get(id_pag)
                if cp is not None:
                    for cu in cp.unidades_evidencia:
                        unidades_candidatas[cu.id_unidade] = cu
        else:
            for cu in res_base.candidatos_unidade:
                if cu.id_pagina in conjunto_pags:
                    unidades_candidatas[cu.id_unidade] = cu

        if not unidades_candidatas:
            return [], [], []

        avaliadas: list[tuple[PontuacaoCandidatoAlinhamento, tuple[str, ...]]] = []
        for cu in unidades_candidatas.values():
            s_sim_u = cu.pontuacao
            s_pag = mapa_score_pag_sel.get(cu.id_pagina, 0.0)
            eh_visual = (
                cu.tipo_unidade in TIPOS_UNIDADES_VISUAIS or cu.fonte == "ollama"
            )
            s_vis_u = s_sim_u if eh_visual else 0.0

            if usa_hierarquia:
                s_final_u = round(
                    min(
                        1.0,
                        0.7 * s_sim_u + 0.3 * s_pag + peso_vis_efetivo * s_vis_u,
                    ),
                    4,
                )
            else:
                s_final_u = round(s_sim_u, 4)

            avaliadas.append(
                (
                    PontuacaoCandidatoAlinhamento(
                        id_item=cu.id_unidade,
                        id_pagina=cu.id_pagina,
                        numero_pagina=cu.numero_pagina,
                        tipo_unidade=cu.tipo_unidade,
                        ordem_leitura=cu.ordem_leitura,
                        pontuacao_similaridade=s_sim_u,
                        pontuacao_temporal=s_pag if usa_hierarquia else 0.0,
                        pontuacao_visual=s_vis_u,
                        pontuacao_final=s_final_u,
                        selecionado=False,
                    ),
                    cu.ids_evidencias,
                )
            )

        avaliadas.sort(
            key=lambda x: (x[0].pontuacao_final, x[0].pontuacao_similaridade),
            reverse=True,
        )
        melhor_u = avaliadas[0][0].pontuacao_final
        corte_u = max(
            self.limiar_abstencao,
            round(melhor_u * self.pesos.fator_multirrotulo, 4),
        )

        finais_u: list[PontuacaoCandidatoAlinhamento] = []
        ids_u_sel: list[str] = []
        evidencias_extras: list[str] = []

        for item_u, evs in avaliadas:
            selecionar = (
                len(ids_u_sel) < self.max_unidades
                and item_u.pontuacao_final >= corte_u
                and item_u.pontuacao_similaridade > 0.0
            )
            if selecionar:
                ids_u_sel.append(item_u.id_item)
                evidencias_extras.extend(evs)
            finais_u.append(
                PontuacaoCandidatoAlinhamento(
                    id_item=item_u.id_item,
                    id_pagina=item_u.id_pagina,
                    numero_pagina=item_u.numero_pagina,
                    tipo_unidade=item_u.tipo_unidade,
                    ordem_leitura=item_u.ordem_leitura,
                    pontuacao_similaridade=item_u.pontuacao_similaridade,
                    pontuacao_temporal=item_u.pontuacao_temporal,
                    pontuacao_visual=item_u.pontuacao_visual,
                    pontuacao_final=item_u.pontuacao_final,
                    selecionado=selecionar,
                )
            )

        return finais_u, ids_u_sel, evidencias_extras

    def _formatar_justificativa_alinhamento(
        self,
        topo_pag: PontuacaoCandidatoAlinhamento,
        gamma_abstencao: float | None,
    ) -> str:
        base = (
            f"estrategia={self.estrategia} | pag_topo={topo_pag.id_item}"
            f"(final={topo_pag.pontuacao_final:.4f}, "
            f"sim={topo_pag.pontuacao_similaridade:.4f}, "
            f"temp={topo_pag.pontuacao_temporal:.4f}, "
            f"vis={topo_pag.pontuacao_visual:.4f})"
        )
        if gamma_abstencao is not None:
            base += f" | gamma_abs={gamma_abstencao:.4f}"
        return base
