from .CaixaDelimitadora import CaixaDelimitadora
from .EvidenciaRecuperacao import (
    CandidatoPagina,
    CandidatoUnidade,
    ResultadoRecuperacaoIntervalo,
    agregar_pontuacao_unidades,
    combinar_pontuacao_pagina,
)
from .IntervaloTempo import IntervaloTempo
from .MetadadosAudio import MetadadosAudio
from .ProvenienciaDocumento import ProvenienciaDocumento
from .TipoRelacao import OrigemAlinhamento, StatusAlinhamento, TipoRelacao

__all__ = [
    "CaixaDelimitadora",
    "CandidatoPagina",
    "CandidatoUnidade",
    "IntervaloTempo",
    "MetadadosAudio",
    "OrigemAlinhamento",
    "ProvenienciaDocumento",
    "ResultadoRecuperacaoIntervalo",
    "StatusAlinhamento",
    "TipoRelacao",
    "agregar_pontuacao_unidades",
    "combinar_pontuacao_pagina",
]
