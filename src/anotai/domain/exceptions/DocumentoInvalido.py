from anotai.domain.exceptions.ErroProcessamentoDocumento import ErroProcessamentoDocumento


class DocumentoInvalido(ErroProcessamentoDocumento):
    """O arquivo não existe, não é PDF ou não pode ser aberto."""
