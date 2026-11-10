from collections.abc import Sequence
from dataclasses import dataclass

from .intervalo_tempo import IntervaloTempo


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


@dataclass(frozen=True, slots=True)
class CandidatoUnidade:
    id_unidade: str
    id_pagina: str
    numero_pagina: int
    tipo_unidade: str
    ordem_leitura: int
    texto: str | None
    pontuacao: float
    estrategia: str
    fonte: str
    ids_evidencias: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CandidatoPagina:
    id_pagina: str
    numero_pagina: int
    texto: str
    pontuacao: float
    pontuacao_direta: float
    pontuacao_unidades: float
    estrategia: str
    unidades_evidencia: tuple[CandidatoUnidade, ...] = ()


@dataclass(frozen=True, slots=True)
class ResultadoRecuperacaoIntervalo:
    id_intervalo: str
    ordem_intervalo: int
    texto_intervalo: str
    intervalo_tempo: IntervaloTempo
    id_documento: str
    estrategia: str
    candidatos_pagina: tuple[CandidatoPagina, ...]
    candidatos_unidade: tuple[CandidatoUnidade, ...]
    abstido: bool
    limiar_abstencao: float
    maior_pontuacao: float
    motivo_abstencao: str | None = None
