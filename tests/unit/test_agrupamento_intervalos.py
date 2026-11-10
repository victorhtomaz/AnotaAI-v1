from anotai.application.use_cases.agrupar_intervalos import AgrupadorIntervalos
from anotai.domain.entities.SegmentoTranscricao import SegmentoTranscricao
from anotai.domain.value_objects.IntervaloTempo import IntervaloTempo


def criar_segmento(ordem: int, inicio: float, fim: float, texto: str) -> SegmentoTranscricao:
    return SegmentoTranscricao(
        id_segmento=f"seg-{ordem}",
        id_aula="aula-1",
        texto=texto,
        intervalo=IntervaloTempo(inicio, fim),
        ordem=ordem,
    )


def test_agrupamento_vazio() -> None:
    agrupador = AgrupadorIntervalos()
    assert agrupador.agrupar([], "aula-1") == []


def test_agrupamento_com_pouca_duracao_permanece_junto() -> None:
    # Dois segmentos curtos sem atingir a duração mínima (10s)
    segs = [
        criar_segmento(1, 0.0, 3.0, "Olá pessoal."),
        criar_segmento(2, 3.5, 6.0, "Hoje falaremos de IA."),
    ]
    agrupador = AgrupadorIntervalos(duracao_minima=10.0, duracao_maxima=45.0)
    intervalos = agrupador.agrupar(segs, "aula-1")

    assert len(intervalos) == 1
    assert intervalos[0].intervalo.inicio == 0.0
    assert intervalos[0].intervalo.fim == 6.0
    assert intervalos[0].texto == "Olá pessoal. Hoje falaremos de IA."
    assert intervalos[0].ids_segmentos == ["seg-1", "seg-2"]


def test_agrupamento_divide_por_silencio_quando_atinge_minimo() -> None:
    segs = [
        criar_segmento(1, 0.0, 6.0, "Primeira parte da introdução."),
        criar_segmento(2, 6.0, 11.0, "Segunda parte terminando a introdução."),
        # Pausa de 3 segundos (11.0 até 14.0 >= limiar_silencio 1.5) e duracao já passou de 10s
        criar_segmento(3, 14.0, 20.0, "Agora vamos para o segundo tópico."),
    ]
    agrupador = AgrupadorIntervalos(limiar_silencio=1.5, duracao_minima=10.0, duracao_maxima=45.0)
    intervalos = agrupador.agrupar(segs, "aula-1")

    assert len(intervalos) == 2
    assert intervalos[0].intervalo.inicio == 0.0
    assert intervalos[0].intervalo.fim == 11.0
    assert intervalos[0].ids_segmentos == ["seg-1", "seg-2"]

    assert intervalos[1].intervalo.inicio == 14.0
    assert intervalos[1].intervalo.fim == 20.0
    assert intervalos[1].ids_segmentos == ["seg-3"]


def test_agrupamento_divide_ao_atingir_duracao_maxima() -> None:
    segs = [
        criar_segmento(1, 0.0, 20.0, "Fala contínua sem pausas longas 1"),
        criar_segmento(2, 20.0, 35.0, "Fala contínua sem pausas longas 2"),
        # Adicionar o próximo segmento levaria a duração de 0.0 a 55.0 (> max 45.0)
        criar_segmento(3, 35.0, 55.0, "Fala contínua que ultrapassa a janela máxima"),
    ]
    agrupador = AgrupadorIntervalos(duracao_minima=10.0, duracao_maxima=45.0)
    intervalos = agrupador.agrupar(segs, "aula-1")

    assert len(intervalos) == 2
    assert intervalos[0].intervalo.fim == 35.0
    assert intervalos[1].intervalo.inicio == 35.0
    assert intervalos[1].intervalo.fim == 55.0
