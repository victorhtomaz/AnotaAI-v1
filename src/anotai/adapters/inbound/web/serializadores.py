from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException

from anotai.application.ports import (
    RenderizadorDocumento,
    RepositorioAlinhamento,
    RepositorioAula,
    RepositorioDocumento,
)
from anotai.application.use_cases import ConsultarAcervo
from anotai.bootstrap import criar_repositorios
from anotai.config import Settings
from anotai.domain.entities import Alinhamento, Aula, Documento
from anotai.domain.value_objects import OrigemAlinhamento, StatusAlinhamento

from .gerenciador_processamento import GerenciadorProcessamento, TarefaProcessamento
from .schemas import (
    CaixaDelimitadoraSchema,
    DocumentoGrafoResponse,
    EtapaStatusSchema,
    IntervaloExplicativoSchema,
    JobStatusResponse,
    MetricaJustificativaSchema,
    PaginaDocumentoSchema,
    SegmentoTranscricaoSchema,
    UnidadeDocumentoSchema,
    VinculoIntervaloSchema,
)

PADRAO_PAG_TOPO = re.compile(
    r"pag_topo=([^\s(]+)\(final=([0-9.]+),\s*sim=([0-9.]+),\s*temp=([0-9.]+),\s*vis=([0-9.]+)\)"
)
PADRAO_GAMMA_ABS = re.compile(r"gamma_abs=([0-9.]+)")


def abrir_repositorios(
    cfg: Settings,
) -> tuple[RepositorioDocumento, RepositorioAula, RepositorioAlinhamento]:
    """Abre os repositórios pela raiz de composição validando se o banco existe."""
    banco_path = Path(cfg.database_path)
    if not banco_path.exists():
        raise HTTPException(status_code=404, detail="Banco de dados não inicializado.")
    return criar_repositorios(banco_path)


def serializar_tarefa(tarefa: TarefaProcessamento) -> JobStatusResponse:
    """Converte uma TarefaProcessamento interna para o schema REST de status."""
    etapas = {
        etapa.chave: EtapaStatusSchema(
            chave=etapa.chave,
            titulo=etapa.titulo,
            estado=etapa.estado,
            rotulo_estado=etapa.rotulo_estado,
            resumo=etapa.resumo,
            metricas=dict(etapa.metricas),
            mensagem_erro=etapa.mensagem_erro,
        )
        for etapa in tarefa.etapas
    }
    return JobStatusResponse(
        job_id=tarefa.id_job,
        criado_em=tarefa.criado_em,
        status_geral=tarefa.status_geral,
        rotulo_geral=tarefa.rotulo_geral,
        em_andamento=tarefa.em_andamento,
        id_documento=tarefa.id_documento,
        id_aula=tarefa.id_aula,
        nome_arquivo_pdf=tarefa.nome_arquivo_pdf,
        nome_arquivo_audio=tarefa.nome_arquivo_audio,
        mensagem_erro=tarefa.mensagem_erro,
        etapas=etapas,
    )


def extrair_metricas_justificativa(
    justificativa: str | None,
    mapa_num_pagina: dict[str, int] | None = None,
) -> list[MetricaJustificativaSchema] | None:
    """Extrai métricas estruturadas da justificativa do algoritmo para exibição na UI."""
    texto = (justificativa or "").strip()
    if not texto:
        return None
    match_pag = PADRAO_PAG_TOPO.search(texto)
    if not match_pag:
        return None

    id_pag, final_v, sim_v, temp_v, vis_v = match_pag.groups()

    def _pct(valor_str: str) -> str:
        return f"{round(float(valor_str) * 100)}%"

    num_pag = mapa_num_pagina.get(id_pag) if mapa_num_pagina else None
    itens = [
        MetricaJustificativaSchema(rotulo="Conf.", valor=_pct(final_v)),
        MetricaJustificativaSchema(
            rotulo="Princ.",
            valor=f"Pág. {num_pag}" if num_pag is not None else id_pag,
        ),
        MetricaJustificativaSchema(rotulo="Texto", valor=_pct(sim_v)),
        MetricaJustificativaSchema(rotulo="Temp.", valor=_pct(temp_v)),
    ]
    if float(vis_v) > 0:
        itens.append(MetricaJustificativaSchema(rotulo="Visual", valor=_pct(vis_v)))
    match_gamma = PADRAO_GAMMA_ABS.search(texto)
    if match_gamma:
        itens.append(MetricaJustificativaSchema(rotulo="Abst.", valor=_pct(match_gamma.group(1))))
    return itens


def serializar_vinculo(
    alinhamento: Alinhamento,
    mapa_num_pagina: dict[str, int] | None = None,
) -> VinculoIntervaloSchema:
    """Converte um Alinhamento do domínio para o schema de vínculo consumido na SPA."""
    eh_manual = alinhamento.origem == OrigemAlinhamento.MANUAL.value
    return VinculoIntervaloSchema(
        id_alinhamento=alinhamento.id_alinhamento,
        id_intervalo=alinhamento.id_intervalo,
        id_documento=alinhamento.id_documento,
        id_aula=alinhamento.id_aula,
        ids_paginas=list(alinhamento.ids_paginas),
        ids_unidades=list(alinhamento.ids_unidades),
        status=alinhamento.status,
        abstido=alinhamento.status == StatusAlinhamento.ABSTIDO.value,
        origem=alinhamento.origem,
        automatico=not eh_manual,
        manual=eh_manual,
        estrategia=alinhamento.estrategia,
        tipo_relacao=alinhamento.tipo_relacao,
        confianca=alinhamento.confianca,
        justificativa=alinhamento.justificativa,
        metricas=extrair_metricas_justificativa(alinhamento.justificativa, mapa_num_pagina),
    )


def obter_dimensoes_paginas_pdf(
    documento: Documento, renderizador: RenderizadorDocumento
) -> dict[int, tuple[float, float]]:
    """Obtém largura e altura via porta de renderização ou estima pelas bounding boxes."""
    dimensoes = dict(renderizador.obter_dimensoes_paginas(Path(documento.uri_origem)))

    for pag in documento.paginas:
        if pag.numero_pagina not in dimensoes:
            max_x = max([u.caixa.x1 for u in pag.unidades if u.caixa is not None] + [612.0])
            max_y = max([u.caixa.y1 for u in pag.unidades if u.caixa is not None] + [792.0])
            dimensoes[pag.numero_pagina] = (float(max_x), float(max_y))
    return dimensoes


def normalizar_caixa(
    x0: float, y0: float, x1: float, y1: float, largura: float, altura: float
) -> CaixaDelimitadoraSchema:
    """Normaliza coordenadas absolutas de PDF para percentuais (0..100%) para o overlay SVG."""
    larg = max(largura, 1.0)
    alt = max(altura, 1.0)
    x_pct = round(max(0.0, min(100.0, (x0 / larg) * 100.0)), 4)
    y_pct = round(max(0.0, min(100.0, (y0 / alt) * 100.0)), 4)
    w_pct = round(max(0.0, min(100.0 - x_pct, ((x1 - x0) / larg) * 100.0)), 4)
    h_pct = round(max(0.0, min(100.0 - y_pct, ((y1 - y0) / alt) * 100.0)), 4)
    return CaixaDelimitadoraSchema(
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        x_pct=x_pct,
        y_pct=y_pct,
        w_pct=w_pct,
        h_pct=h_pct,
    )


def resolver_aula_para_documento(
    id_documento: str,
    id_aula_param: str | None,
    repo_doc: RepositorioDocumento,
    repo_aula: RepositorioAula,
    repo_alin: RepositorioAlinhamento,
    gestor: GerenciadorProcessamento,
    *,
    aulas_precarregadas: list[Aula] | None = None,
) -> tuple[Aula | None, list[Alinhamento]]:
    """Delega ao caso de uso ConsultarAcervo e traduz ausência explícita para HTTP 404."""
    consulta = ConsultarAcervo(repo_doc=repo_doc, repo_aula=repo_aula, repo_alin=repo_alin)
    id_aula_sugerida = gestor.obter_aula_associada(id_documento)
    try:
        return consulta.resolver_aula_para_documento(
            id_documento=id_documento,
            id_aula_param=id_aula_param,
            id_aula_sugerida=id_aula_sugerida,
            aulas_precarregadas=aulas_precarregadas,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def construir_grafo_documento(
    documento: Documento,
    aula: Aula | None,
    alinhamentos: list[Alinhamento],
    renderizador: RenderizadorDocumento,
) -> DocumentoGrafoResponse:
    """Monta páginas, unidades, intervalos e vínculos para o Explorador."""
    dimensoes = obter_dimensoes_paginas_pdf(documento, renderizador)
    mapa_num_pagina = {pag.id_pagina: pag.numero_pagina for pag in documento.paginas}

    paginas_schema: list[PaginaDocumentoSchema] = []
    for pag in sorted(documento.paginas, key=lambda p: p.numero_pagina):
        largura, altura = dimensoes.get(pag.numero_pagina, (612.0, 792.0))
        unidades_schema = [
            UnidadeDocumentoSchema(
                id_unidade=u.id_unidade,
                id_pagina=u.id_pagina,
                numero_pagina=pag.numero_pagina,
                tipo=u.tipo,
                texto=u.texto,
                ordem_leitura=u.ordem_leitura,
                fonte=u.fonte,
                eh_decorativa=u.eh_decorativa,
                caixa=(
                    normalizar_caixa(
                        u.caixa.x0,
                        u.caixa.y0,
                        u.caixa.x1,
                        u.caixa.y1,
                        largura,
                        altura,
                    )
                    if u.caixa is not None
                    else None
                ),
            )
            for u in sorted(pag.unidades, key=lambda x: x.ordem_leitura)
        ]
        paginas_schema.append(
            PaginaDocumentoSchema(
                id_pagina=pag.id_pagina,
                numero_pagina=pag.numero_pagina,
                metodo_extracao=pag.metodo_extracao,
                largura=largura,
                altura=altura,
                texto_normalizado=pag.texto_normalizado,
                unidades=unidades_schema,
            )
        )

    vinculos_serializados = [
        serializar_vinculo(a, mapa_num_pagina=mapa_num_pagina) for a in alinhamentos
    ]
    mapa_serializados = {v.id_alinhamento: v for v in vinculos_serializados}
    ativos_dominio = ConsultarAcervo.selecionar_vinculos_ativos(alinhamentos)
    vinculo_ativo_por_intervalo = {
        id_int: mapa_serializados[alin.id_alinhamento]
        for id_int, alin in ativos_dominio.items()
    }

    segmentos_schema: list[SegmentoTranscricaoSchema] = []
    intervalos_schema: list[IntervaloExplicativoSchema] = []
    url_audio: str | None = None

    if aula is not None:
        segmentos_schema = [
            SegmentoTranscricaoSchema(
                id_segmento=s.id_segmento,
                ordem=s.ordem,
                inicio=s.intervalo.inicio,
                fim=s.intervalo.fim,
                texto=s.texto,
                confianca=s.confianca,
            )
            for s in sorted(aula.segmentos, key=lambda x: x.ordem)
        ]
        intervalos_schema = [
            IntervaloExplicativoSchema(
                id_intervalo=i.id_intervalo,
                ordem=i.ordem,
                inicio=i.intervalo.inicio,
                fim=i.intervalo.fim,
                duracao=i.intervalo.duracao,
                texto=i.texto,
                ids_segmentos=list(i.ids_segmentos),
                vinculo=vinculo_ativo_por_intervalo.get(i.id_intervalo),
            )
            for i in sorted(aula.intervalos, key=lambda x: x.ordem)
        ]
        url_audio = f"/api/documentos/{documento.id_documento}/audio?id_aula={aula.id_aula}"

    return DocumentoGrafoResponse(
        id_documento=documento.id_documento,
        titulo_documento=documento.titulo,
        uri_origem_pdf=documento.uri_origem,
        metodo_extracao=documento.proveniencia.metodo_extracao,
        id_aula=aula.id_aula if aula else None,
        titulo_aula=aula.titulo if aula else None,
        duracao_audio=aula.metadados.duracao if aula else None,
        idioma_aula=aula.idioma if aula else None,
        url_pdf=f"/api/documentos/{documento.id_documento}/pdf",
        url_audio=url_audio,
        paginas=paginas_schema,
        segmentos=segmentos_schema,
        intervalos=intervalos_schema,
        vinculos=vinculos_serializados,
    )
