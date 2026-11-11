import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    ollama_url: str = "http://localhost:11434"
    visual_model: str = "qwen3-vl:8b"
    processed_directory: str = "data/processados"
    database_path: str = "data/processados/anotai.sqlite"
    visual_temperature: float = 0.0
    visual_seed: int = 42
    visual_think: bool = False
    ollama_keep_alive: str = "5m"
    embedding_model: str = "bge-m3:567m"
    whisperx_model: str = "large-v3"
    whisperx_device: str = "cuda"
    whisperx_compute_type: str = "float16"
    whisperx_align_phonemes: bool = False
    raw_transcripts_directory: str = "data/processados/transcricoes_brutas"
    interval_silence_threshold: float = 1.5
    interval_min_duration: float = 10.0
    interval_max_duration: float = 45.0
    abstention_threshold: float = 0.0
    alignment_similarity_weight: float = 0.75
    alignment_temporal_weight: float = 0.20
    alignment_visual_weight: float = 0.05
    alignment_temporal_window: int = 2
    hmm_emission_temperature: float = 0.15
    hmm_emission_floor: float = 0.01
    hmm_abstention_emission_prior: float = 0.15
    hmm_stay_weight: float = 1.0
    hmm_adjacent_weight: float = 0.6
    hmm_jump_base_weight: float = 0.15
    hmm_jump_decay: float = 0.35
    hmm_jump_floor: float = 0.02

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv()
        return cls(
            ollama_url=os.getenv("ANOTAI_OLLAMA_URL", cls.ollama_url),
            visual_model=os.getenv("ANOTAI_OLLAMA_MODELO_VISUAL", cls.visual_model),
            processed_directory=os.getenv("ANOTAI_DIRETORIO_PROCESSADOS", cls.processed_directory),
            database_path=os.getenv("ANOTAI_BANCO", cls.database_path),
            visual_temperature=float(
                os.getenv("ANOTAI_OLLAMA_TEMPERATURA", cls.visual_temperature)
            ),
            visual_seed=int(os.getenv("ANOTAI_OLLAMA_SEED", cls.visual_seed)),
            visual_think=os.getenv("ANOTAI_OLLAMA_PENSAR", "false").lower() == "true",
            ollama_keep_alive=os.getenv("ANOTAI_OLLAMA_KEEP_ALIVE", cls.ollama_keep_alive),
            embedding_model=os.getenv("ANOTAI_OLLAMA_MODELO_EMBEDDING", cls.embedding_model),
            whisperx_model=os.getenv("ANOTAI_WHISPERX_MODELO", cls.whisperx_model),
            whisperx_device=os.getenv("ANOTAI_WHISPERX_DISPOSITIVO", cls.whisperx_device),
            whisperx_compute_type=os.getenv(
                "ANOTAI_WHISPERX_TIPO_COMPUTACAO", cls.whisperx_compute_type
            ),
            whisperx_align_phonemes=(
                os.getenv("ANOTAI_WHISPERX_ALINHAR_FONEMAS", "false").lower() == "true"
            ),
            raw_transcripts_directory=os.getenv(
                "ANOTAI_DIRETORIO_BRUTOS", cls.raw_transcripts_directory
            ),
            interval_silence_threshold=float(
                os.getenv("ANOTAI_INTERVALO_LIMIAR_SILENCIO", cls.interval_silence_threshold)
            ),
            interval_min_duration=float(
                os.getenv("ANOTAI_INTERVALO_DURACAO_MINIMA", cls.interval_min_duration)
            ),
            interval_max_duration=float(
                os.getenv("ANOTAI_INTERVALO_DURACAO_MAXIMA", cls.interval_max_duration)
            ),
            abstention_threshold=float(
                os.getenv("ANOTAI_LIMIAR_ABSTENCAO", cls.abstention_threshold)
            ),
            alignment_similarity_weight=float(
                os.getenv(
                    "ANOTAI_ALINHAMENTO_PESO_SIMILARIDADE", cls.alignment_similarity_weight
                )
            ),
            alignment_temporal_weight=float(
                os.getenv("ANOTAI_ALINHAMENTO_PESO_TEMPORAL", cls.alignment_temporal_weight)
            ),
            alignment_visual_weight=float(
                os.getenv("ANOTAI_ALINHAMENTO_PESO_VISUAL", cls.alignment_visual_weight)
            ),
            alignment_temporal_window=int(
                os.getenv("ANOTAI_ALINHAMENTO_JANELA_TEMPORAL", cls.alignment_temporal_window)
            ),
            hmm_emission_temperature=float(
                os.getenv("ANOTAI_HMM_TEMPERATURA_EMISSAO", cls.hmm_emission_temperature)
            ),
            hmm_emission_floor=float(
                os.getenv("ANOTAI_HMM_PISO_EMISSAO", cls.hmm_emission_floor)
            ),
            hmm_abstention_emission_prior=float(
                os.getenv("ANOTAI_HMM_PRIOR_ABSTENCAO", cls.hmm_abstention_emission_prior)
            ),
            hmm_stay_weight=float(
                os.getenv("ANOTAI_HMM_PESO_PERMANENCIA", cls.hmm_stay_weight)
            ),
            hmm_adjacent_weight=float(
                os.getenv("ANOTAI_HMM_PESO_ADJACENTE", cls.hmm_adjacent_weight)
            ),
            hmm_jump_base_weight=float(
                os.getenv("ANOTAI_HMM_PESO_SALTO_BASE", cls.hmm_jump_base_weight)
            ),
            hmm_jump_decay=float(
                os.getenv("ANOTAI_HMM_DECAIMENTO_SALTO", cls.hmm_jump_decay)
            ),
            hmm_jump_floor=float(
                os.getenv("ANOTAI_HMM_PISO_SALTO", cls.hmm_jump_floor)
            ),
        )
