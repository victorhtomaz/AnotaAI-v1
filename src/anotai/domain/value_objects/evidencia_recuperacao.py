from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .intervalo_tempo import IntervaloTempo

if TYPE_CHECKING:
    from anotai.domain.entities.alinhamento import Alinhamento

TIPOS_UNIDADES_VISUAIS = frozenset({"figure", "table", "graph", "formula"})


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


@dataclass(frozen=True, slots=True)
class PesosAlinhamento:
    peso_similaridade: float = 0.75
    peso_temporal: float = 0.20
    peso_visual: float = 0.05
    janela_temporal: int = 2
    fator_multirrotulo: float = 0.75


@dataclass(frozen=True, slots=True)
class ParametrosHMM:
    temperatura_emissao: float = 0.15
    piso_emissao: float = 0.01
    prior_abstencao_emissao: float = 0.15
    peso_permanencia: float = 1.0
    peso_adjacente: float = 0.6
    peso_salto_base: float = 0.15
    decaimento_salto: float = 0.35
    piso_salto: float = 0.02
    prob_transicao_abstencao: float = 0.10
    prob_permanencia_abstencao: float = 0.40


@dataclass(frozen=True, slots=True)
class PontuacaoCandidatoAlinhamento:
    id_item: str
    numero_pagina: int
    pontuacao_similaridade: float
    pontuacao_temporal: float
    pontuacao_visual: float
    pontuacao_final: float
    selecionado: bool
    id_pagina: str | None = None
    tipo_unidade: str | None = None
    ordem_leitura: int | None = None


@dataclass(frozen=True, slots=True)
class ResultadoAlinhamentoIntervalo:
    alinhamento: Alinhamento
    ordem_intervalo: int
    texto_intervalo: str
    intervalo_tempo: IntervaloTempo
    candidatos_pagina: tuple[PontuacaoCandidatoAlinhamento, ...] = ()
    candidatos_unidade: tuple[PontuacaoCandidatoAlinhamento, ...] = ()
    probabilidade_abstencao_hmm: float | None = None


from anotai.domain.services.pontuacao_alinhamento import (  # noqa: E402
    agregar_pontuacao_unidades,
    calcular_contexto_temporal_pagina,
    calcular_evidencia_visual_pagina,
    calcular_posteriores_hmm,
    combinar_pontuacao_pagina,
    combinar_sinais_alinhamento,
)

__all__ = [
    "TIPOS_UNIDADES_VISUAIS",
    "CandidatoPagina",
    "CandidatoUnidade",
    "ParametrosHMM",
    "PesosAlinhamento",
    "PontuacaoCandidatoAlinhamento",
    "ResultadoAlinhamentoIntervalo",
    "ResultadoRecuperacaoIntervalo",
    "agregar_pontuacao_unidades",
    "calcular_contexto_temporal_pagina",
    "calcular_evidencia_visual_pagina",
    "calcular_posteriores_hmm",
    "combinar_pontuacao_pagina",
    "combinar_sinais_alinhamento",
]
