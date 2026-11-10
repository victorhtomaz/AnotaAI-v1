from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class SegmentoBrutoASR:
    texto: str
    inicio: float
    fim: float
    confianca: float | None = None
    palavras: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ResultadoTranscricao:
    idioma: str
    segmentos: list[SegmentoBrutoASR]
    carga_bruta: dict[str, Any]


class ProvedorTranscricao(Protocol):
    def transcrever(self, caminho_audio: Path) -> ResultadoTranscricao:
        """Transcreve o áudio gerando segmentos com timestamps e a carga bruta de resposta."""
        ...
