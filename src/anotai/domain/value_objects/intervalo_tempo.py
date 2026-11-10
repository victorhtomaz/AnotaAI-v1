from dataclasses import dataclass


@dataclass(frozen=True)
class IntervaloTempo:
    inicio: float
    fim: float

    def __post_init__(self) -> None:
        if self.inicio < 0.0:
            raise ValueError(f"tempo inicial não pode ser negativo: {self.inicio}")
        if self.fim <= self.inicio:
            raise ValueError(
                f"tempo final ({self.fim}) deve ser estritamente maior que inicial ({self.inicio})"
            )

    @property
    def duracao(self) -> float:
        return round(self.fim - self.inicio, 4)

    def sobrepoe(self, outro: "IntervaloTempo") -> bool:
        return max(self.inicio, outro.inicio) < min(self.fim, outro.fim)

    def iou(self, outro: "IntervaloTempo") -> float:
        intersecao = max(0.0, min(self.fim, outro.fim) - max(self.inicio, outro.inicio))
        uniao = max(self.fim, outro.fim) - min(self.inicio, outro.inicio)
        return round(intersecao / uniao, 4) if uniao > 0 else 0.0

    @staticmethod
    def formatar_segundos(segundos: float) -> str:
        horas = int(segundos // 3600)
        minutos = int((segundos % 3600) // 60)
        segs = segundos % 60
        return f"{horas:02d}:{minutos:02d}:{segs:06.3f}"

    def formatar(self) -> str:
        return f"{self.formatar_segundos(self.inicio)} -> {self.formatar_segundos(self.fim)}"
