"""Composição de dependências e inicialização do sistema."""

from .composicao import (
    construir_indices_busca,
    criar_analisador_visual,
    criar_extrator_documento,
    criar_inspetor_audio,
    criar_provedor_transcricao,
    criar_renderizador_documento,
    criar_repositorios,
    obter_classes_repositorios,
)

__all__ = [
    "construir_indices_busca",
    "criar_analisador_visual",
    "criar_extrator_documento",
    "criar_inspetor_audio",
    "criar_provedor_transcricao",
    "criar_renderizador_documento",
    "criar_repositorios",
    "obter_classes_repositorios",
]
