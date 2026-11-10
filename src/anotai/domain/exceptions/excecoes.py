"""Exceções canônicas do domínio do AnotaAI."""


class ErroAnotaAI(Exception):
    """Exceção base para todos os erros de domínio do AnotaAI."""


class ErroIntegridade(ErroAnotaAI):
    """Exceção levantada quando invariantes estruturais ou referenciais são violadas."""


class ErroAudio(ErroAnotaAI):
    """Erro base para falhas relacionadas a processamento de áudio."""


class AudioInvalido(ErroAudio):
    """O arquivo de áudio/vídeo não existe, formato não é suportado ou está corrompido."""


class ErroTranscricao(ErroAnotaAI):
    """Falha durante o processo de transcrição automática de áudio."""


class ErroProcessamentoDocumento(ErroAnotaAI):
    """Erro base para falhas no processamento de documentos PDF."""


class DocumentoInvalido(ErroProcessamentoDocumento):
    """O arquivo não existe, não é PDF ou não pode ser aberto."""


class MetodoExtracaoNaoSuportado(ErroProcessamentoDocumento):
    """O método de extração solicitado não é suportado."""


class ErroAnaliseVisual(ErroProcessamentoDocumento):
    """A análise visual não pôde ser concluída ou validada."""


class ErroBusca(ErroAnotaAI):
    """Erro ao indexar ou recuperar informações nos índices de busca."""


__all__ = [
    "AudioInvalido",
    "DocumentoInvalido",
    "ErroAnaliseVisual",
    "ErroAnotaAI",
    "ErroAudio",
    "ErroBusca",
    "ErroIntegridade",
    "ErroProcessamentoDocumento",
    "ErroTranscricao",
    "MetodoExtracaoNaoSuportado",
]
