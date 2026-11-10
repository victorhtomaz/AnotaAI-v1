from dataclasses import dataclass, field

from anotai.domain.value_objects import IntervaloTempo


@dataclass
class IntervaloExplicativo:
    id_intervalo: str
    id_aula: str
    texto: str
    intervalo: IntervaloTempo
    ordem: int
    ids_segmentos: list[str] = field(default_factory=list)
    tipo: str = "explanation"
    notas: str | None = None

    TIPOS_VALIDOS = {"explanation", "reference", "contextualization"}

    def __post_init__(self) -> None:
        if not self.id_intervalo:
            raise ValueError("id_intervalo não pode ser vazio")
        if not self.id_aula:
            raise ValueError("id_aula não pode ser vazio")
        if self.ordem < 1:
            raise ValueError("ordem do intervalo deve ser positiva (>= 1)")
        if self.tipo not in self.TIPOS_VALIDOS:
            raise ValueError(f"tipo de intervalo explicativo inválido: {self.tipo}")
