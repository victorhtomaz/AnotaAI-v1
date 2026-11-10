from dataclasses import dataclass


@dataclass(frozen=True)
class MetadadosAudio:
    duracao: float
    taxa_amostragem: int
    canais: int
    formato: str
    codec: str | None = None
    taxa_bits: int | None = None

    def __post_init__(self) -> None:
        if self.duracao <= 0.0:
            raise ValueError(f"duração do áudio deve ser positiva: {self.duracao}")
        if self.taxa_amostragem <= 0:
            raise ValueError(f"taxa de amostragem deve ser positiva: {self.taxa_amostragem}")
        if self.canais <= 0:
            raise ValueError(f"quantidade de canais deve ser positiva: {self.canais}")
        if not self.formato:
            raise ValueError("formato do áudio não pode ser vazio")
