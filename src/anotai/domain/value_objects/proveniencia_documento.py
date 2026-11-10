from dataclasses import dataclass


@dataclass(frozen=True)
class ProvenienciaDocumento:
    uri_origem: str
    metodo_extracao: str
    versao_pipeline: str
    modelo: str | None = None
    configuracao: dict[str, str] | None = None
    prompt: str | None = None
    executado_em: str | None = None
