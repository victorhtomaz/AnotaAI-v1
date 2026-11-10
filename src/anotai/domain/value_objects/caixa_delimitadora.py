from dataclasses import dataclass


@dataclass(frozen=True)
class CaixaDelimitadora:
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("bbox deve ter coordenadas ordenadas")
