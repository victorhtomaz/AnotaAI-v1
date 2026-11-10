import pytest

from anotai.domain.value_objects import IntervaloTempo


def test_intervalo_tempo_valido() -> None:
    intervalo = IntervaloTempo(inicio=0.0, fim=5.5)
    assert intervalo.inicio == 0.0
    assert intervalo.fim == 5.5
    assert intervalo.duracao == 5.5


def test_intervalo_tempo_rejeita_inicio_negativo() -> None:
    with pytest.raises(ValueError, match="tempo inicial não pode ser negativo"):
        IntervaloTempo(inicio=-1.0, fim=5.0)


def test_intervalo_tempo_rejeita_fim_menor_ou_igual_inicio() -> None:
    with pytest.raises(ValueError, match="estritamente maior"):
        IntervaloTempo(inicio=5.0, fim=5.0)

    with pytest.raises(ValueError, match="estritamente maior"):
        IntervaloTempo(inicio=6.0, fim=5.0)


def test_intervalo_tempo_sobreposicao() -> None:
    i1 = IntervaloTempo(0.0, 10.0)
    i2 = IntervaloTempo(5.0, 15.0)
    i3 = IntervaloTempo(10.0, 20.0)
    i4 = IntervaloTempo(12.0, 20.0)

    assert i1.sobrepoe(i2) is True
    assert i2.sobrepoe(i1) is True
    assert i1.sobrepoe(i3) is False  # pontas se tocando não sobrepõem
    assert i1.sobrepoe(i4) is False


def test_intervalo_tempo_iou() -> None:
    i1 = IntervaloTempo(0.0, 10.0)
    i2 = IntervaloTempo(5.0, 15.0)
    # intersecao = [5, 10] (5.0), uniao = [0, 15] (15.0) -> 5/15 = 0.3333
    assert i1.iou(i2) == 0.3333

    # Totalmente idênticos -> 1.0
    assert i1.iou(i1) == 1.0

    # Disjuntos -> 0.0
    i3 = IntervaloTempo(20.0, 30.0)
    assert i1.iou(i3) == 0.0


def test_intervalo_tempo_formatacao() -> None:
    intervalo = IntervaloTempo(65.5, 3661.2)
    assert intervalo.formatar() == "00:01:05.500 -> 01:01:01.200"
