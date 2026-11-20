from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anotai.domain.value_objects.evidencia_recuperacao import (
        CandidatoPagina,
        ParametrosHMM,
        PesosAlinhamento,
        ResultadoRecuperacaoIntervalo,
    )


def agregar_pontuacao_unidades(pontuacoes: Sequence[float]) -> float:
    """Combina as pontuações de unidades de uma mesma página valorizando múltiplos blocos.

    Utiliza os até 3 maiores scores positivos da página:
    s = min(1.0, u1 + 0.25 * u2 + 0.15 * u3)
    """
    positivas = sorted([p for p in pontuacoes if p > 0.0], reverse=True)
    if not positivas:
        return 0.0

    u1 = positivas[0]
    u2 = positivas[1] if len(positivas) > 1 else 0.0
    u3 = positivas[2] if len(positivas) > 2 else 0.0

    agregado = u1 + 0.25 * u2 + 0.15 * u3
    return round(min(1.0, max(0.0, agregado)), 4)


def combinar_pontuacao_pagina(pontuacao_direta: float, pontuacao_unidades: float) -> float:
    """Combina a evidência textual direta da página com a evidência agregada de suas unidades.

    Se houver suporte em ambos os níveis, calcula a média ponderada (0.5 direta + 0.5 unidades).
    Caso contrário, adota o valor máximo disponível para não penalizar páginas sem unidades finas.
    """
    direta = max(0.0, min(1.0, pontuacao_direta))
    unidades = max(0.0, min(1.0, pontuacao_unidades))

    if direta > 0.0 and unidades > 0.0:
        combinada = 0.5 * direta + 0.5 * unidades
    else:
        combinada = max(direta, unidades)

    return round(combinada, 4)


def calcular_evidencia_visual_pagina(candidato_pagina: CandidatoPagina) -> float:
    from anotai.domain.value_objects.evidencia_recuperacao import TIPOS_UNIDADES_VISUAIS

    pontuacoes_visuais = [
        u.pontuacao
        for u in candidato_pagina.unidades_evidencia
        if u.tipo_unidade in TIPOS_UNIDADES_VISUAIS or u.fonte == "ollama"
    ]
    return round(min(1.0, max(pontuacoes_visuais, default=0.0)), 4)


def calcular_contexto_temporal_pagina(
    idx_atual: int,
    resultados_base: Sequence[ResultadoRecuperacaoIntervalo],
    id_pagina: str,
    mapa_num_pagina: dict[str, int],
    janela: int = 2,
) -> float:
    """Calcula suporte temporal flexível a partir dos intervalos vizinhos sem impor monotonicidade.

    Permite permanência/revisita na mesma página (fator 1.0) e transições para páginas
    adjacentes anteriores ou seguintes (fator 0.6), sem penalizar saltos distantes.
    """
    if janela <= 0 or len(resultados_base) <= 1 or id_pagina not in mapa_num_pagina:
        return 0.0

    num_alvo = mapa_num_pagina[id_pagina]
    inicio_j = max(0, idx_atual - janela)
    fim_j = min(len(resultados_base) - 1, idx_atual + janela)

    soma_ponderada = 0.0
    soma_pesos = 0.0

    for k in range(inicio_j, fim_j + 1):
        if k == idx_atual:
            continue
        peso_dist = 1.0 / abs(idx_atual - k)
        soma_pesos += peso_dist

        melhor_suporte_vizinho = 0.0
        for cand_viz in resultados_base[k].candidatos_pagina:
            num_viz = mapa_num_pagina.get(cand_viz.id_pagina, cand_viz.numero_pagina)
            delta_pag = abs(num_alvo - num_viz)
            if delta_pag == 0:
                fator_transicao = 1.0
            elif delta_pag == 1:
                fator_transicao = 0.6
            else:
                fator_transicao = 0.0

            if fator_transicao > 0.0:
                suporte = cand_viz.pontuacao * fator_transicao
                if suporte > melhor_suporte_vizinho:
                    melhor_suporte_vizinho = suporte

        soma_ponderada += peso_dist * melhor_suporte_vizinho

    if soma_pesos <= 0.0:
        return 0.0

    return round(min(1.0, max(0.0, soma_ponderada / soma_pesos)), 4)


def combinar_sinais_alinhamento(
    similaridade: float,
    temporal: float,
    visual: float,
    pesos: PesosAlinhamento,
) -> float:
    """Combina similaridade documental com reforço temporal e visual configurável.

    Mantém a escala da similaridade direta quando não há suporte temporal ou visual para não
    penalizar referências não sequenciais isoladas ou páginas puramente textuais.
    """
    sim = max(0.0, min(1.0, similaridade))
    if sim <= 0.0:
        return 0.0

    temp = max(0.0, min(1.0, temporal))
    vis = max(0.0, min(1.0, visual))

    fator_sim = 1.0 if pesos.peso_similaridade > 0.0 else 0.0
    combinada = (
        fator_sim * sim
        + max(0.0, pesos.peso_temporal) * temp
        + max(0.0, pesos.peso_visual) * vis
    )
    return round(min(1.0, max(0.0, combinada)), 4)


def calcular_posteriores_hmm(
    resultados_base: Sequence[ResultadoRecuperacaoIntervalo],
    paginas_ordenadas: Sequence[tuple[str, int]],
    params_hmm: ParametrosHMM | None = None,
    peso_visual: float = 0.0,
) -> list[tuple[dict[str, float], float]]:
    """Executa inferência forward-backward em um HMM ergódico sobre páginas + estado ∅.

    Retorna uma lista (uma posição por intervalo) contendo `(gamma_por_pagina, gamma_abstencao)`.
    """
    if params_hmm is None:
        from anotai.domain.value_objects.evidencia_recuperacao import ParametrosHMM

        params_hmm = ParametrosHMM()
    n_intervalos = len(resultados_base)
    if n_intervalos == 0:
        return []

    n_paginas = len(paginas_ordenadas)
    if n_paginas == 0:
        return [({}, 1.0) for _ in range(n_intervalos)]

    n_estados = n_paginas + 1
    idx_abstencao = n_paginas
    tau = max(1e-4, float(params_hmm.temperatura_emissao))
    piso_emissao = max(1e-6, min(0.5, float(params_hmm.piso_emissao)))
    prob_abs = max(0.0, min(0.95, float(params_hmm.prob_transicao_abstencao)))
    prob_perm_abs = max(0.0, min(0.95, float(params_hmm.prob_permanencia_abstencao)))

    # 1. Matriz de transição A (n_estados x n_estados) sem monotonicidade rígida
    transicao: list[list[float]] = [[0.0] * n_estados for _ in range(n_estados)]
    for i in range(n_paginas):
        num_i = paginas_ordenadas[i][1]
        pesos_linha: list[float] = []
        for j in range(n_paginas):
            num_j = paginas_ordenadas[j][1]
            delta = abs(num_i - num_j)
            if delta == 0:
                w = max(1e-6, params_hmm.peso_permanencia)
            elif delta == 1:
                w = max(1e-6, params_hmm.peso_adjacente)
            else:
                dec = params_hmm.peso_salto_base * math.exp(
                    -max(0.0, params_hmm.decaimento_salto) * (delta - 1)
                )
                w = max(params_hmm.piso_salto, dec, 1e-6)
            pesos_linha.append(w)

        soma_w = sum(pesos_linha) or 1.0
        massa_paginas = 1.0 - prob_abs
        for j in range(n_paginas):
            transicao[i][j] = massa_paginas * (pesos_linha[j] / soma_w)
        transicao[i][idx_abstencao] = prob_abs

    massa_saida_abs = (1.0 - prob_perm_abs) / n_paginas
    for j in range(n_paginas):
        transicao[idx_abstencao][j] = massa_saida_abs
    transicao[idx_abstencao][idx_abstencao] = prob_perm_abs

    # 2. Distribuição inicial pi
    pi = [(1.0 - prob_abs) / n_paginas for _ in range(n_paginas)] + [prob_abs]

    # 3. Matriz de emissões B (n_intervalos x n_estados) via softmax(score / tau)
    emissoes: list[list[float]] = []
    for res in resultados_base:
        mapa_cand = {c.id_pagina: c for c in res.candidatos_pagina}
        scores_brutos: list[float] = []
        maior_sim_bruta = 0.0

        for id_pag, _ in paginas_ordenadas:
            cand = mapa_cand.get(id_pag)
            if cand is not None and cand.pontuacao > 0.0:
                if cand.pontuacao > maior_sim_bruta:
                    maior_sim_bruta = cand.pontuacao
                s_vis = calcular_evidencia_visual_pagina(cand) if peso_visual > 0.0 else 0.0
                score_pag = min(1.0, max(piso_emissao, cand.pontuacao + peso_visual * s_vis))
            else:
                score_pag = piso_emissao
            scores_brutos.append(score_pag)

        # Normaliza scores de página preservando teto em 1.0 quando houver saturação
        fator_norm = max(1.0, max(scores_brutos, default=1.0))
        scores_norm = [s / fator_norm for s in scores_brutos]

        if maior_sim_bruta <= 0.0:
            score_abs = 1.0
        else:
            score_abs = max(piso_emissao, min(1.0, params_hmm.prior_abstencao_emissao))
        scores_norm.append(score_abs)

        logits = [s / tau for s in scores_norm]
        max_logit = max(logits)
        exps = [math.exp(lg - max_logit) for lg in logits]
        soma_exp = sum(exps) or 1.0
        emissoes.append([v / soma_exp for v in exps])

    # 4. Passo Forward escalado
    alfa: list[list[float]] = [[0.0] * n_estados for _ in range(n_intervalos)]
    for s in range(n_estados):
        alfa[0][s] = pi[s] * emissoes[0][s]
    soma_a0 = sum(alfa[0]) or 1.0
    alfa[0] = [v / soma_a0 for v in alfa[0]]

    for t in range(1, n_intervalos):
        for s in range(n_estados):
            soma_ant = sum(alfa[t - 1][i] * transicao[i][s] for i in range(n_estados))
            alfa[t][s] = emissoes[t][s] * soma_ant
        soma_at = sum(alfa[t]) or 1.0
        alfa[t] = [v / soma_at for v in alfa[t]]

    # 5. Passo Backward escalado
    beta: list[list[float]] = [[0.0] * n_estados for _ in range(n_intervalos)]
    beta[-1] = [1.0 / n_estados for _ in range(n_estados)]

    for t in range(n_intervalos - 2, -1, -1):
        for s in range(n_estados):
            beta[t][s] = sum(
                transicao[s][j] * emissoes[t + 1][j] * beta[t + 1][j]
                for j in range(n_estados)
            )
        soma_bt = sum(beta[t]) or 1.0
        beta[t] = [v / soma_bt for v in beta[t]]

    # 6. Posteriores marginais gamma[t, s]
    posteriores: list[tuple[dict[str, float], float]] = []
    for t in range(n_intervalos):
        bruto = [alfa[t][s] * beta[t][s] for s in range(n_estados)]
        soma_g = sum(bruto) or 1.0
        gamma = [v / soma_g for v in bruto]
        mapa_gamma_pag = {
            paginas_ordenadas[j][0]: round(gamma[j], 4) for j in range(n_paginas)
        }
        gamma_abs = round(gamma[idx_abstencao], 4)
        posteriores.append((mapa_gamma_pag, gamma_abs))

    return posteriores


__all__ = [
    "agregar_pontuacao_unidades",
    "calcular_contexto_temporal_pagina",
    "calcular_evidencia_visual_pagina",
    "calcular_posteriores_hmm",
    "combinar_pontuacao_pagina",
    "combinar_sinais_alinhamento",
]
