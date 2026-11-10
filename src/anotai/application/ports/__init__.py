from .analisador_visual import AnalisadorVisual
from .extrator_documento import ExtratorDocumento
from .inspetor_audio import InspetorAudio
from .provedor_transcricao import ProvedorTranscricao, ResultadoTranscricao, SegmentoBrutoASR
from .repositorio_alinhamento import RepositorioAlinhamento
from .repositorio_anotacao import RepositorioAnotacao
from .repositorio_aula import RepositorioAula
from .repositorio_documento import RepositorioDocumento

__all__ = [
    "AnalisadorVisual",
    "ExtratorDocumento",
    "InspetorAudio",
    "ProvedorTranscricao",
    "RepositorioAlinhamento",
    "RepositorioAnotacao",
    "RepositorioAula",
    "RepositorioDocumento",
    "ResultadoTranscricao",
    "SegmentoBrutoASR",
]
