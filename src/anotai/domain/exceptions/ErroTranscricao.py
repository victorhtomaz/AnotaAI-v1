from anotai.domain.exceptions.ErroAudio import ErroAudio


class ErroTranscricao(ErroAudio):
    """Falha durante o processo de transcrição ou alinhamento temporal do ASR."""
