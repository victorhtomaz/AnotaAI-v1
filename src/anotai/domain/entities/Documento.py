from dataclasses import dataclass, field

from anotai.domain.value_objects.CaixaDelimitadora import CaixaDelimitadora
from anotai.domain.value_objects.ProvenienciaDocumento import ProvenienciaDocumento


@dataclass
class UnidadeDocumento:
    id_unidade: str
    id_documento: str
    id_pagina: str
    tipo: str
    texto: str | None
    ordem_leitura: int
    caixa: CaixaDelimitadora | None
    fonte: str
    ids_evidencias: list[str] = field(default_factory=list)
    eh_decorativa: bool = False

    TIPOS_VALIDOS = {
        "title",
        "paragraph",
        "formula",
        "table",
        "graph",
        "figure",
        "caption",
        "block",
        "group",
    }
    TIPOS_VISUAIS_VALIDOS = {"figure", "table", "graph", "formula"}

    def __post_init__(self) -> None:
        if self.tipo not in self.TIPOS_VALIDOS:
            raise ValueError(f"tipo de unidade inválido: {self.tipo}")
        if self.ordem_leitura < 1:
            raise ValueError("ordem de leitura deve ser positiva")

    @property
    def participa_alinhamento(self) -> bool:
        return not self.eh_decorativa


@dataclass
class PaginaDocumento:
    id_pagina: str
    numero_pagina: int
    texto_nativo: str
    texto_normalizado: str
    metodo_extracao: str
    unidades: list[UnidadeDocumento] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.numero_pagina < 1:
            raise ValueError("número de página deve ser positivo")


@dataclass
class Documento:
    id_documento: str
    uri_origem: str
    titulo: str
    paginas: list[PaginaDocumento]
    versao_processamento: str
    proveniencia: ProvenienciaDocumento
