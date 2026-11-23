from __future__ import annotations

from pydantic import BaseModel, Field


class JobCriadoResponse(BaseModel):
    job_id: str
    status: str


class EtapaStatusSchema(BaseModel):
    chave: str
    titulo: str
    estado: str
    rotulo_estado: str
    resumo: str
    metricas: dict[str, str] = Field(default_factory=dict)
    mensagem_erro: str | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    criado_em: str
    status_geral: str
    rotulo_geral: str
    em_andamento: bool
    id_documento: str | None = None
    id_aula: str | None = None
    nome_arquivo_pdf: str | None = None
    nome_arquivo_audio: str | None = None
    mensagem_erro: str | None = None
    etapas: dict[str, EtapaStatusSchema]


class OpcoesPadraoResponse(BaseModel):
    executar_pdf: bool
    executar_transcricao: bool
    executar_alinhamento: bool
    metodo_pdf: str
    provedor_visual: str
    modelo_visual: str
    temperatura_visual: float
    seed_visual: int
    pensar_visual: bool
    provedor_transcricao: str
    idioma_transcricao: str
    modelo_whisperx: str
    dispositivo_whisperx: str
    tipo_computacao: str
    alinhar_fonemas: bool
    limiar_silencio: float
    duracao_minima_intervalo: float
    duracao_maxima_intervalo: float
    modo_alinhamento: str
    estrategia_alinhamento: str
    estrategia_base: str
    modelo_temporal: str
    provedor_embedding: str
    modelo_embedding: str
    limiar_abstencao: float
    max_paginas: int
    max_unidades: int
    peso_similaridade: float
    peso_temporal: float
    peso_visual: float
    janela_temporal: int
    temperatura_hmm: float


class CaixaDelimitadoraSchema(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float
    x_pct: float
    y_pct: float
    w_pct: float
    h_pct: float


class UnidadeDocumentoSchema(BaseModel):
    id_unidade: str
    id_pagina: str
    numero_pagina: int
    tipo: str
    texto: str | None = None
    ordem_leitura: int
    fonte: str
    eh_decorativa: bool
    caixa: CaixaDelimitadoraSchema | None = None


class PaginaDocumentoSchema(BaseModel):
    id_pagina: str
    numero_pagina: int
    metodo_extracao: str
    largura: float
    altura: float
    texto_normalizado: str
    unidades: list[UnidadeDocumentoSchema]


class SegmentoTranscricaoSchema(BaseModel):
    id_segmento: str
    ordem: int
    inicio: float
    fim: float
    texto: str
    confianca: float | None = None


class MetricaJustificativaSchema(BaseModel):
    rotulo: str
    valor: str


class VinculoIntervaloSchema(BaseModel):
    id_alinhamento: str
    id_intervalo: str
    id_documento: str
    id_aula: str
    ids_paginas: list[str]
    ids_unidades: list[str]
    status: str
    abstido: bool
    origem: str
    automatico: bool
    manual: bool
    estrategia: str
    tipo_relacao: str | None = None
    confianca: float
    justificativa: str | None = None
    metricas: list[MetricaJustificativaSchema] | None = None


class IntervaloExplicativoSchema(BaseModel):
    id_intervalo: str
    ordem: int
    inicio: float
    fim: float
    duracao: float
    texto: str
    ids_segmentos: list[str]
    vinculo: VinculoIntervaloSchema | None = None


class ResumoDocumentoItemSchema(BaseModel):
    id_documento: str
    titulo_documento: str
    id_aula: str | None = None
    titulo_aula: str | None = None
    paginas: int
    unidades: int
    paginas_ocr: int
    metodo_extracao: str
    intervalos: int = 0
    alinhamentos: int = 0
    tem_audio: bool = False


class ResumoAulaItemSchema(BaseModel):
    id_aula: str
    titulo: str
    duracao: float
    segmentos: int
    intervalos: int
    alinhamentos: int


class DocumentoGrafoResponse(BaseModel):
    id_documento: str
    titulo_documento: str
    uri_origem_pdf: str
    metodo_extracao: str
    id_aula: str | None = None
    titulo_aula: str | None = None
    duracao_audio: float | None = None
    idioma_aula: str | None = None
    url_pdf: str
    url_audio: str | None = None
    paginas: list[PaginaDocumentoSchema]
    segmentos: list[SegmentoTranscricaoSchema]
    intervalos: list[IntervaloExplicativoSchema]
    vinculos: list[VinculoIntervaloSchema]


class CriarVinculoRequest(BaseModel):
    id_intervalo: str
    ids_paginas: list[str] = Field(default_factory=list)
    ids_unidades: list[str] = Field(default_factory=list)
    abster: bool = False
    tipo_relacao: str | None = "direct"
    justificativa: str | None = None
    id_aula: str | None = None
