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
from anotai.domain.exceptions import ErroAnaliseVisual, ErroBusca, ErroTranscricao


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
    provedor: str | None = None,
) -> Any:
    """Instancia o analisador visual (Ollama por padrão ou Google AI Studio) configurado."""
    provedor_efetivo = (
        (provedor or getattr(settings, "visual_provider", "ollama") or "ollama")
        .strip()
        .lower()
    )

    if provedor_efetivo == "google_ai_studio":
        chave = getattr(settings, "google_api_key", "").strip()
        if not chave:
            raise ErroAnaliseVisual(
                "Chave do Google AI Studio não configurada: defina "
                "ANOTAI_GOOGLE_API_KEY (ou GEMINI_API_KEY)."
            )

        modelo_google = (
            getattr(settings, "google_visual_model", "gemma-4-31b-it").strip()
            or "gemma-4-31b-it"
        )

        classe = analisador_cls
        if classe is None:
            try:
                import google.genai  # noqa: F401
            except ImportError as exc:
                raise ErroAnaliseVisual(
                    "SDK do Google GenAI não instalado. Execute: uv sync --extra google"
                ) from exc

            from anotai.adapters.outbound.google import AnalisadorVisualGoogleAIStudio

            classe = AnalisadorVisualGoogleAIStudio

        return classe(
            chave=chave,
            modelo=modelo_google,
            temperatura=temperatura,
            modelos_fallback=tuple(
                getattr(
                    settings,
                    "google_visual_fallback_models",
                    ("gemma-4-26b-a4b-it", "gemini-2.5-flash-lite"),
                )
            ),
            max_tentativas=int(getattr(settings, "google_max_retries", 3)),
            backoff_inicial_segundos=float(
                getattr(settings, "google_backoff_initial_seconds", 2.0)
            ),
            intervalo_entre_requisicoes_segundos=float(
                getattr(settings, "google_request_interval_seconds", 0.5)
            ),
            max_concorrencia=int(getattr(settings, "google_max_concurrency", 2)),
        )

    if provedor_efetivo != "ollama":
        raise ErroAnaliseVisual(f"Provedor de análise visual não suportado: '{provedor_efetivo}'")

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
    settings: Settings | None = None,
    provedor: str | None = None,
    idioma: str | None = None,
) -> Any:
    """Instancia o provedor de transcrição automática (WhisperX por padrão ou Azure Speech)."""
    provedor_efetivo = (
        (
            provedor
            or (getattr(settings, "transcription_provider", "whisperx") if settings else "whisperx")
            or "whisperx"
        )
        .strip()
        .lower()
    )

    if provedor_efetivo == "azure_speech":
        chave = getattr(settings, "azure_speech_key", "").strip() if settings else ""
        regiao = getattr(settings, "azure_speech_region", "").strip() if settings else ""
        endpoint = getattr(settings, "azure_speech_endpoint", "").strip() if settings else ""
        if not chave or not (regiao or endpoint):
            raise ErroTranscricao(
                "Credenciais do Azure Speech não configuradas: defina "
                "ANOTAI_AZURE_SPEECH_KEY e ANOTAI_AZURE_SPEECH_REGION (ou ENDPOINT)."
            )

        idioma_efetivo = (
            idioma
            or (getattr(settings, "azure_speech_language", "pt-BR") if settings else "pt-BR")
            or "pt-BR"
        )
        timestamps_palavras = (
            bool(getattr(settings, "azure_speech_word_timestamps", True))
            if settings
            else True
        )

        classe = provedor_cls
        if classe is None:
            try:
                import azure.cognitiveservices.speech  # noqa: F401
            except ImportError as exc:
                raise ErroTranscricao(
                    "SDK do Azure Speech não instalado. Execute: uv sync --extra azure"
                ) from exc

            from anotai.adapters.outbound.azure import ProvedorAzureSpeech

            classe = ProvedorAzureSpeech

        return classe(
            chave=chave,
            regiao=regiao,
            idioma=idioma_efetivo,
            endpoint=endpoint,
            timestamps_palavras=timestamps_palavras,
        )

    if provedor_efetivo != "whisperx":
        raise ErroTranscricao(f"Provedor de transcrição não suportado: '{provedor_efetivo}'")

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


def criar_provedor_embedding(
    settings: Settings,
    *,
    modelo_override: str | None = None,
    provedor: str | None = None,
    provedor_cls: Any = None,
) -> Any:
    """Instancia o provedor de embeddings (Ollama por padrão ou Google AI Studio)."""
    provedor_efetivo = (
        (provedor or getattr(settings, "embedding_provider", "ollama") or "ollama")
        .strip()
        .lower()
    )

    if provedor_efetivo == "google_ai_studio":
        chave = getattr(settings, "google_api_key", "").strip()
        if not chave:
            raise ErroBusca(
                "Chave do Google AI Studio não configurada: defina "
                "ANOTAI_GOOGLE_API_KEY (ou GEMINI_API_KEY)."
            )

        modelo_google = (
            (
                modelo_override
                or getattr(settings, "google_embedding_model", "gemini-embedding-001")
            ).strip()
            or "gemini-embedding-001"
        )
        dimensoes = getattr(settings, "google_embedding_dimensions", None)

        classe = provedor_cls
        if classe is None:
            try:
                import google.genai  # noqa: F401
            except ImportError as exc:
                raise ErroBusca(
                    "SDK do Google GenAI não instalado. Execute: uv sync --extra google"
                ) from exc

            from anotai.adapters.outbound.google import ProvedorEmbeddingGoogleAIStudio

            classe = ProvedorEmbeddingGoogleAIStudio

        return classe(
            chave=chave,
            modelo=modelo_google,
            dimensoes_saida=dimensoes,
            max_tentativas=int(getattr(settings, "google_max_retries", 3)),
            backoff_inicial_segundos=float(
                getattr(settings, "google_backoff_initial_seconds", 2.0)
            ),
            intervalo_entre_requisicoes_segundos=float(
                getattr(settings, "google_request_interval_seconds", 0.5)
            ),
            max_concorrencia=int(getattr(settings, "google_max_concurrency", 2)),
        )

    if provedor_efetivo != "ollama":
        raise ErroBusca(f"Provedor de embedding não suportado: '{provedor_efetivo}'")

    from ollama import Client

    classe = provedor_cls
    if classe is None:
        from anotai.adapters.outbound.ollama.provedor_embedding import ProvedorEmbeddingOllama

        classe = ProvedorEmbeddingOllama

    modelo_emb = (modelo_override or settings.embedding_model).strip() or settings.embedding_model
    return classe(
        cliente=Client(host=settings.ollama_url),
        modelo=modelo_emb,
        manter_vivo=settings.ollama_keep_alive,
    )


def construir_indices_busca(
    estrategia_base: str,
    settings: Settings,
    modelo_override: str | None = None,
    provedor_override: str | None = None,
) -> tuple[Any, Any]:
    """Constrói os índices de busca de páginas e unidades conforme a estratégia escolhida."""
    from anotai.adapters.outbound.search import IndiceBM25, IndiceEmbeddings, IndiceHibrido

    if estrategia_base == "bm25":
        return IndiceBM25(), IndiceBM25()

    if estrategia_base in ("embedding", "hybrid"):
        provedor = criar_provedor_embedding(
            settings,
            modelo_override=modelo_override,
            provedor=provedor_override,
        )
        if estrategia_base == "embedding":
            return IndiceEmbeddings(provedor), IndiceEmbeddings(provedor)
        return (
            IndiceHibrido(IndiceBM25(), IndiceEmbeddings(provedor)),
            IndiceHibrido(IndiceBM25(), IndiceEmbeddings(provedor)),
        )

    raise ValueError(f"Estratégia base de busca não suportada: '{estrategia_base}'")
