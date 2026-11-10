from anotai.domain.entities import Aula, Documento
from anotai.domain.value_objects import ResultadoRecuperacaoIntervalo


def formatar_aula_texto(
    aula: Aula, detalhado: bool = False, intervalo_alvo: int | None = None
) -> str:
    """Formata os dados e a transcrição da aula para exibição textual no terminal."""
    linhas = [
        "=" * 80,
        "AnotaAI — Transcrição de Aula",
        "=" * 80,
        f"ID da Aula: {aula.id_aula}",
        f"Título: {aula.titulo}",
        f"Arquivo: {aula.caminho_arquivo.name}",
        f"Duração: {aula.metadados.duracao:.2f}s | Idioma: {aula.idioma or 'não informado'}",
        f"Segmentos: {len(aula.segmentos)} | Intervalos Explicativos: {len(aula.intervalos)}",
        "=" * 80,
    ]

    intervalos_para_exibir = aula.intervalos
    if intervalo_alvo is not None:
        intervalos_filtrados = [i for i in aula.intervalos if i.ordem == intervalo_alvo]
        if not intervalos_filtrados:
            linhas.append(f"Aviso: Intervalo explicativo #{intervalo_alvo} não encontrado.")
            return "\n".join(linhas)
        intervalos_para_exibir = intervalos_filtrados
        linhas.append(f"Visualizando Intervalo Específico #{intervalo_alvo}:")
    else:
        linhas.append("INTERVALOS EXPLICATIVOS:")

    mapa_segmentos = {s.id_segmento: s for s in aula.segmentos}

    for inter in intervalos_para_exibir:
        linhas.append("-" * 80)
        linhas.append(
            f"[{inter.ordem:02d}] {inter.intervalo.formatar()} "
            f"({inter.intervalo.duracao:.2f}s) [{len(inter.ids_segmentos)} segmentos]"
        )
        linhas.append(f'     "{inter.texto}"')

        if detalhado or intervalo_alvo is not None:
            linhas.append("     Segmentos atômicos:")
            for sid in inter.ids_segmentos:
                seg = mapa_segmentos.get(sid)
                if seg:
                    conf = f" (conf: {seg.confianca:.2f})" if seg.confianca is not None else ""
                    linhas.append(f'       - [{seg.intervalo.formatar()}]{conf} "{seg.texto}"')

    linhas.append("=" * 80)
    return "\n".join(linhas)


def formatar_recuperacao_texto(
    aula: Aula,
    documento: Documento,
    resultados: list[ResultadoRecuperacaoIntervalo],
) -> str:
    """Formata evidências e candidatos recuperados para exibição textual no terminal."""
    estrategia = resultados[0].estrategia if resultados else "desconhecida"
    limiar = resultados[0].limiar_abstencao if resultados else 0.0

    linhas = [
        "=" * 80,
        "AnotaAI — Recuperação e Busca de Candidatos",
        "=" * 80,
        f"Aula: {aula.id_aula} ({aula.titulo})",
        f"Documento: {documento.id_documento} ({documento.titulo})",
        f"Estratégia: {estrategia.upper()} | Limiar de Abstenção: {limiar:.4f}",
        "Aviso: As pontuações indicam similaridade e não probabilidade calibrada.",
        "=" * 80,
    ]

    for res in resultados:
        linhas.append("-" * 80)
        linhas.append(
            f"[{res.ordem_intervalo:02d}] {res.intervalo_tempo.formatar()} "
            f'"{res.texto_intervalo}"'
        )

        if res.abstido:
            linhas.append(f"     [ABSTENÇÃO] {res.motivo_abstencao}")
            continue

        linhas.append("     Páginas sugeridas:")
        for cand_p in res.candidatos_pagina:
            linhas.append(
                f"       - Pág. {cand_p.numero_pagina:02d} "
                f"(score: {cand_p.pontuacao:.4f} [direto: {cand_p.pontuacao_direta:.4f}, "
                f"unidades: {cand_p.pontuacao_unidades:.4f}])"
            )

        if res.candidatos_unidade:
            linhas.append("     Unidades sugeridas:")
            for cand_u in res.candidatos_unidade:
                txt = (cand_u.texto or "").strip()
                if len(txt) > 80:
                    txt = txt[:77] + "..."
                linhas.append(
                    f"       - [Pág. {cand_u.numero_pagina:02d} | u#{cand_u.ordem_leitura:02d} "
                    f"{cand_u.tipo_unidade} | {cand_u.fonte}] "
                    f'(score: {cand_u.pontuacao:.4f}) "{txt}"'
                )

    linhas.append("=" * 80)
    return "\n".join(linhas)

