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
        )
