from enum import StrEnum


class TipoRelacao(StrEnum):
    DIRETA = "direct"
    REFERENCIA = "reference"
    CONTEXTUAL = "contextual"

    @classmethod
    def normalizar(cls, valor: str | None) -> "TipoRelacao | None":
        if valor is None:
            return None
        chave = str(valor).strip().lower()
        mapeamento = {
            "direct": cls.DIRETA,
            "direta": cls.DIRETA,
            "explanation": cls.DIRETA,
            "explicacao": cls.DIRETA,
            "explicacao_direta": cls.DIRETA,
            "reference": cls.REFERENCIA,
            "referencia": cls.REFERENCIA,
            "contextual": cls.CONTEXTUAL,
            "contextualization": cls.CONTEXTUAL,
            "contextualizacao": cls.CONTEXTUAL,
        }
        if chave in mapeamento:
            return mapeamento[chave]
        raise ValueError(
            f"Tipo de relação inválido: '{valor}'. Esperado um dos: "
            f"{', '.join(v.value for v in cls)}"
        )


class StatusAlinhamento(StrEnum):
    ALINHADO = "aligned"
    ABSTIDO = "abstained"

    @classmethod
    def normalizar(cls, valor: str) -> "StatusAlinhamento":
        chave = str(valor).strip().lower()
        for membro in cls:
            if membro.value == chave:
                return membro
        raise ValueError(
            f"Status de alinhamento inválido: '{valor}'. Esperado: 'aligned' ou 'abstained'"
        )


class OrigemAlinhamento(StrEnum):
    AUTOMATICO = "automatic"
    MANUAL = "manual"

    @classmethod
    def normalizar(cls, valor: str) -> "OrigemAlinhamento":
        chave = str(valor).strip().lower()
        for membro in cls:
            if membro.value == chave:
                return membro
        raise ValueError(
            f"Origem de alinhamento inválida: '{valor}'. Esperado: 'automatic' ou 'manual'"
        )
