from anotai.domain.exceptions.ErroProcessamentoDocumento import ErroProcessamentoDocumento


class MetodoExtracaoNaoSuportado(ErroProcessamentoDocumento):
    """O método de extração solicitado não é suportado."""
