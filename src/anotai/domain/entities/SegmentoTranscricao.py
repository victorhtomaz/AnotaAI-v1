from dataclasses import dataclass, field

from anotai.domain.value_objects.IntervaloTempo import IntervaloTempo


@dataclass
class SegmentoTranscricao:
    id_segmento: str
    id_aula: str
    texto: str
    intervalo: IntervaloTempo
    ordem: int
    fonte: str = "asr"
    confianca: float | None = None
    palavras: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id_segmento:
            raise ValueError("id_segmento não pode ser vazio")
        if not self.id_aula:
            raise ValueError("id_aula não pode ser vazio")
        if self.ordem < 1:
            raise ValueError("ordem do segmento deve ser positiva (>= 1)")
        if self.fonte not in {"asr", "manual"}:
            raise ValueError(f"fonte inválida: {self.fonte}")
