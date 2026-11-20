"""Serviços de domínio para regras e algoritmos puros."""

from .pontuacao_alinhamento import (
    agregar_pontuacao_unidades,
    calcular_contexto_temporal_pagina,
    calcular_evidencia_visual_pagina,
    calcular_posteriores_hmm,
    combinar_pontuacao_pagina,
    combinar_sinais_alinhamento,
)
from .validador_integridade import ValidadorIntegridade

__all__ = [
    "ValidadorIntegridade",
    "agregar_pontuacao_unidades",
    "calcular_contexto_temporal_pagina",
    "calcular_evidencia_visual_pagina",
    "calcular_posteriores_hmm",
    "combinar_pontuacao_pagina",
    "combinar_sinais_alinhamento",
]
