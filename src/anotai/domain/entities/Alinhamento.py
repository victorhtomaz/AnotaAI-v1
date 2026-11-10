import hashlib
from dataclasses import dataclass, field

from anotai.domain.value_objects.TipoRelacao import (
    OrigemAlinhamento,
    StatusAlinhamento,
    TipoRelacao,
)


@dataclass
class Alinhamento:
    id_alinhamento: str
    id_aula: str
    id_documento: str
    id_intervalo: str
    ids_paginas: list[str] = field(default_factory=list)
    ids_unidades: list[str] = field(default_factory=list)
    status: str = "aligned"
    tipo_relacao: str | None = "direct"
    confianca: float = 0.0
    estrategia: str = "bm25"
    ids_evidencias: list[str] = field(default_factory=list)
    versao_processamento: str = "1.0"
    justificativa: str | None = None
    origem: str = "automatic"

    ESTRATEGIAS_VALIDAS = {
        "bm25",
        "embedding",
        "temporal",
        "hierarchical",
        "hybrid",
        "manual",
    }

    def __post_init__(self) -> None:
        if not self.id_alinhamento:
            raise ValueError("id_alinhamento não pode ser vazio")
        if not self.id_aula:
            raise ValueError("id_aula não pode ser vazio")
        if not self.id_documento:
            raise ValueError("id_documento não pode ser vazio")
        if not self.id_intervalo:
            raise ValueError("id_intervalo não pode ser vazio")

        # Normaliza status e origem
        self.status = StatusAlinhamento.normalizar(self.status).value
        self.origem = OrigemAlinhamento.normalizar(self.origem).value

        # Normaliza tipo_relacao se presente
        if self.tipo_relacao is not None:
            self.tipo_relacao = TipoRelacao.normalizar(self.tipo_relacao).value

        # Deduplicação preservando ordem de relevância
        self.ids_paginas = list(dict.fromkeys(self.ids_paginas))
        self.ids_unidades = list(dict.fromkeys(self.ids_unidades))
        self.ids_evidencias = list(dict.fromkeys(self.ids_evidencias))

        if not (0.0 <= self.confianca <= 1.0):
            raise ValueError(f"confiança deve estar entre 0.0 e 1.0: {self.confianca}")

        if not self.estrategia:
            raise ValueError("estratégia não pode ser vazia")

        if self.status == StatusAlinhamento.ABSTIDO.value:
            if self.ids_paginas or self.ids_unidades:
                raise ValueError(
                    "Alinhamento com status 'abstained' não deve conter páginas ou unidades"
                )
            self.tipo_relacao = None
        else:
            if not self.ids_paginas:
                raise ValueError("Alinhamento com status 'aligned' deve conter ao menos uma página")
            if self.tipo_relacao is None:
                raise ValueError(
                    "Alinhamento com status 'aligned' deve conter um tipo_relacao válido"
                )

    @classmethod
    def gerar_id_estavel(
        cls,
        id_intervalo: str,
        id_documento: str,
        estrategia: str,
        origem: str = "automatic",
    ) -> str:
        dados = f"{id_intervalo}:{id_documento}:{estrategia}:{origem}".encode()
        hash_id = hashlib.sha256(dados).hexdigest()[:12]
        return f"align-{hash_id}"
