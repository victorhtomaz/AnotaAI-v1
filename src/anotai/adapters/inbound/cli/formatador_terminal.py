from anotai.domain.entities.Aula import Aula


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
