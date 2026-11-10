from anotai.domain.exceptions.ErroAudio import ErroAudio


class AudioInvalido(ErroAudio):
    """O arquivo de áudio/vídeo não existe, formato não é suportado ou está corrompido."""
