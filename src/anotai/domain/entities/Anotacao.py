import hashlib
from dataclasses import dataclass, field

from anotai.domain.value_objects.IntervaloTempo import IntervaloTempo
from anotai.domain.value_objects.TipoRelacao import TipoRelacao


@dataclass
class Anotacao:
    id_anotacao: str
    id_aula: str
    id_documento: str
    intervalo: IntervaloTempo
    id_intervalo: str | None = None
    ids_paginas: list[str] = field(default_factory=list)
    ids_unidades: list[str] = field(default_factory=list)
    tipo_relacao: str | None = None
    notas: str | None = None
    versao: str = "1.0"

    def __post_init__(self) -> None:
        if not self.id_anotacao:
            raise ValueError("id_anotacao não pode ser vazio")
        if not self.id_aula:
            raise ValueError("id_aula não pode ser vazio")
        if not self.id_documento:
            raise ValueError("id_documento não pode ser vazio")

        if self.tipo_relacao is not None:
            self.tipo_relacao = TipoRelacao.normalizar(self.tipo_relacao).value

        # Deduplicação preservando ordem
        self.ids_paginas = list(dict.fromkeys(self.ids_paginas))
        self.ids_unidades = list(dict.fromkeys(self.ids_unidades))

    @classmethod
    def gerar_id_estavel(
        cls,
        id_aula: str,
        id_documento: str,
        inicio: float,
        fim: float,
        versao: str = "1.0",
    ) -> str:
        dados = f"{id_aula}:{id_documento}:{inicio:.3f}:{fim:.3f}:{versao}".encode()
        hash_id = hashlib.sha256(dados).hexdigest()[:12]
        return f"annot-{hash_id}"
