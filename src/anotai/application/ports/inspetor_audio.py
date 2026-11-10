from pathlib import Path
from typing import Protocol

from anotai.domain.value_objects.MetadadosAudio import MetadadosAudio


class InspetorAudio(Protocol):
    def inspecionar(self, caminho: Path) -> MetadadosAudio:
        """Inspeciona o arquivo e extrai metadados (duração, canais, taxa de amostragem)."""
        ...

    def extrair_wav_mono_16k(self, caminho_origem: Path, caminho_destino: Path) -> Path:
        """Converte ou extrai o áudio do arquivo original em WAV mono a 16 kHz."""
        ...
