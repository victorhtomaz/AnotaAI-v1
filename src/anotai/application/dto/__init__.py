"""Data Transfer Objects (DTOs) da camada de aplicação."""

from .resultados import (
    CandidatoPagina,
    CandidatoUnidade,
    PontuacaoCandidatoAlinhamento,
    ResultadoAlinhamentoIntervalo,
    ResultadoRecuperacaoIntervalo,
)

__all__ = [
    "CandidatoPagina",
    "CandidatoUnidade",
    "PontuacaoCandidatoAlinhamento",
    "ResultadoAlinhamentoIntervalo",
    "ResultadoRecuperacaoIntervalo",
]
