from dataclasses import dataclass, field

from anotai.domain.value_objects import CaixaDelimitadora, ProvenienciaDocumento


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
    FONTES_OCR_VISUAL = {"ollama", "google_ai_studio"}
    FONTES_VALIDAS = {"native", "inferred", *FONTES_OCR_VISUAL}

    def __post_init__(self) -> None:
        if not self.id_unidade:
            raise ValueError("id_unidade não pode ser vazio")
        if not self.id_documento:
            raise ValueError("id_documento não pode ser vazio")
        if not self.id_pagina:
            raise ValueError("id_pagina não pode ser vazio")
        if self.tipo not in self.TIPOS_VALIDOS:
            raise ValueError(f"tipo de unidade inválido: {self.tipo}")
        if self.ordem_leitura < 1:
            raise ValueError("ordem de leitura deve ser positiva")
        if self.fonte not in self.FONTES_VALIDAS:
            raise ValueError(f"fonte inválida: {self.fonte}")

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

    METODOS_VALIDOS = {"native", "mixed"}

    def __post_init__(self) -> None:
        if not self.id_pagina:
            raise ValueError("id_pagina não pode ser vazio")
        if self.numero_pagina < 1:
            raise ValueError("número de página deve ser positivo")
        if self.metodo_extracao not in self.METODOS_VALIDOS:
            raise ValueError(f"método de extração inválido: {self.metodo_extracao}")


@dataclass
class Documento:
    id_documento: str
    uri_origem: str
    titulo: str
    paginas: list[PaginaDocumento]
    versao_processamento: str
    proveniencia: ProvenienciaDocumento

    def __post_init__(self) -> None:
        if not self.id_documento:
            raise ValueError("id_documento não pode ser vazio")
        if not self.uri_origem:
            raise ValueError("uri_origem não pode ser vazia")
        if not self.titulo:
            raise ValueError("título não pode ser vazio")
