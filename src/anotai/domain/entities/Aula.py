from dataclasses import dataclass, field
from pathlib import Path

from anotai.domain.entities.IntervaloExplicativo import IntervaloExplicativo
from anotai.domain.entities.SegmentoTranscricao import SegmentoTranscricao
from anotai.domain.value_objects.MetadadosAudio import MetadadosAudio


@dataclass
class Aula:
    id_aula: str
    titulo: str
    uri_origem: str
    caminho_arquivo: Path
    metadados: MetadadosAudio
    segmentos: list[SegmentoTranscricao] = field(default_factory=list)
    intervalos: list[IntervaloExplicativo] = field(default_factory=list)
    idioma: str | None = None
    versao_processamento: str = "1.0"

    def __post_init__(self) -> None:
        if not self.id_aula:
            raise ValueError("id_aula não pode ser vazio")
        if not self.titulo:
            raise ValueError("título não pode ser vazio")
