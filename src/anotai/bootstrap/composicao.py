from __future__ import annotations

from pathlib import Path
from typing import Any

from anotai.adapters.outbound.pdf import RenderizadorPDFPyMuPDF
from anotai.adapters.outbound.persistence import (
    RepositorioAlinhamentoSQLite,
    RepositorioAulaSQLite,
    RepositorioDocumentoSQLite,
    inicializar_engine_sqlite,
)
from anotai.application.ports import (
    RenderizadorDocumento,
    RepositorioAlinhamento,
    RepositorioAula,
    RepositorioDocumento,
)
from anotai.config import Settings


def obter_classes_repositorios() -> tuple[type, type, type]:
    """Retorna as implementações concretas padrão dos repositórios SQLite."""
    return (
        RepositorioDocumentoSQLite,
        RepositorioAulaSQLite,
        RepositorioAlinhamentoSQLite,
    )


def criar_repositorios(
    banco_path: Path,
) -> tuple[RepositorioDocumento, RepositorioAula, RepositorioAlinhamento]:
    """Instancia os repositórios concretos de documentos, aulas e alinhamentos."""
    engine = inicializar_engine_sqlite(banco_path)
    return (
        RepositorioDocumentoSQLite(banco_path, engine=engine),
        RepositorioAulaSQLite(banco_path, engine=engine),
        RepositorioAlinhamentoSQLite(banco_path, engine=engine),
    )


def criar_renderizador_documento() -> RenderizadorDocumento:
    """Instancia o adaptador concreto de inspeção e renderização de PDF."""
    return RenderizadorPDFPyMuPDF()


def criar_analisador_visual(
    settings: Settings,
    modelo: str,
    *,
    temperatura: float,
    seed: int,
    pensar: bool,
    analisador_cls: Any = None,
) -> Any:
    """Instancia o analisador visual (Ollama por padrão) com cliente configurado."""
    from ollama import Client

    classe = analisador_cls
    if classe is None:
        from anotai.adapters.outbound.ollama import AnalisadorVisualOllama

        classe = AnalisadorVisualOllama

    return classe(
        Client(host=settings.ollama_url),
        modelo,
        temperatura=temperatura,
        seed=seed,
        pensar=pensar,
        manter_vivo=settings.ollama_keep_alive,
    )


def criar_extrator_documento(analisador: Any = None, extrator_cls: Any = None) -> Any:
    """Instancia o extrator de documentos PDF."""
    classe = extrator_cls
    if classe is None:
        from anotai.adapters.outbound.pdf import ExtratorPDF

        classe = ExtratorPDF
    return classe(analisador)


def criar_inspetor_audio(inspetor_cls: Any = None) -> Any:
    """Instancia o inspetor técnico de mídia/áudio."""
    classe = inspetor_cls
    if classe is None:
        from anotai.adapters.outbound.audio import InspetorFFmpeg

        classe = InspetorFFmpeg
    return classe()


def criar_provedor_transcricao(
    *,
    modelo: str,
    dispositivo: str,
    tipo_computacao: str,
    alinhar_fonemas: bool,
    provedor_cls: Any = None,
) -> Any:
    """Instancia o provedor de transcrição automática (ASR)."""
    classe = provedor_cls
    if classe is None:
        from anotai.adapters.outbound.audio import ProvedorWhisperX

        classe = ProvedorWhisperX
    return classe(
        modelo=modelo,
        dispositivo=dispositivo,
        tipo_computacao=tipo_computacao,
        alinhar_fonemas=alinhar_fonemas,
    )


def construir_indices_busca(
    estrategia_base: str, settings: Settings, modelo_override: str | None = None
) -> tuple[Any, Any]:
    """Constrói os índices de busca de páginas e unidades conforme a estratégia escolhida."""
    from anotai.adapters.outbound.search import IndiceBM25, IndiceEmbeddings, IndiceHibrido

    if estrategia_base == "bm25":
        return IndiceBM25(), IndiceBM25()

    if estrategia_base in ("embedding", "hybrid"):
        from ollama import Client

        from anotai.adapters.outbound.ollama.provedor_embedding import ProvedorEmbeddingOllama

        modelo_emb = modelo_override or settings.embedding_model
        provedor = ProvedorEmbeddingOllama(
            cliente=Client(host=settings.ollama_url),
            modelo=modelo_emb,
            manter_vivo=settings.ollama_keep_alive,
        )
        if estrategia_base == "embedding":
            return IndiceEmbeddings(provedor), IndiceEmbeddings(provedor)
        return (
            IndiceHibrido(IndiceBM25(), IndiceEmbeddings(provedor)),
            IndiceHibrido(IndiceBM25(), IndiceEmbeddings(provedor)),
        )

    raise ValueError(f"Estratégia base de busca não suportada: '{estrategia_base}'")
