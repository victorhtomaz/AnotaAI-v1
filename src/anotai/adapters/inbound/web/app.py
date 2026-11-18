from __future__ import annotations

import mimetypes
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pymupdf
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import FormData, UploadFile

from anotai.adapters.outbound.persistence import (
    RepositorioAlinhamentoSQLite,
    RepositorioAulaSQLite,
    RepositorioDocumentoSQLite,
)
from anotai.application.use_cases import AlinharAula
from anotai.config import Settings
from anotai.domain.entities import Alinhamento, Aula, Documento
from anotai.domain.exceptions import ErroIntegridade
from anotai.domain.value_objects import OrigemAlinhamento, StatusAlinhamento

from .gerenciador_processamento import (
    EXTENSOES_AUDIO_SUPORTADAS,
    GerenciadorProcessamento,
    OpcoesProcessamento,
    TarefaProcessamento,
    salvar_upload_unico,
)
from .schemas import (
    CaixaDelimitadoraSchema,
    CriarVinculoRequest,
    DocumentoGrafoResponse,
    EtapaStatusSchema,
    IntervaloExplicativoSchema,
    JobCriadoResponse,
    JobStatusResponse,
    OpcoesPadraoResponse,
    PaginaDocumentoSchema,
    ResumoAulaItemSchema,
    ResumoDocumentoItemSchema,
    SegmentoTranscricaoSchema,
    UnidadeDocumentoSchema,
    VinculoIntervaloSchema,
)

DIRETORIO_WEB = Path(__file__).resolve().parent
DIRETORIO_STATIC = DIRETORIO_WEB / "static"
TAMANHO_CHUNK_STREAM = 64 * 1024
PADRAO_RANGE_BYTES = re.compile(r"^bytes=(\d*)-(\d*)$")

# Garante MIME type válido para módulos ES (.mjs) no Windows (padrão retorna text/plain).
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("application/javascript", ".js")

EXTENSOES_MIME_AUDIO = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".mkv": "video/x-matroska",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
}


def _flag(form: FormData, chave: str) -> bool:
    return str(form.get(chave, "")).strip().lower() in ("on", "true", "1", "sim")


def _texto(form: FormData, chave: str, padrao: str = "") -> str:
    valor = form.get(chave)
    if valor is None or isinstance(valor, UploadFile):
        return padrao
    return str(valor).strip()


def _inteiro(form: FormData, chave: str, padrao: int, minimo: int | None = None) -> int:
    bruto = _texto(form, chave)
    if not bruto:
        return padrao
    try:
        valor = int(bruto)
    except ValueError as exc:
        raise ValueError(f"Valor inteiro inválido para '{chave}': '{bruto}'.") from exc
    if minimo is not None and valor < minimo:
        raise ValueError(f"O campo '{chave}' deve ser maior ou igual a {minimo}.")
    return valor


def _decimal(
    form: FormData,
    chave: str,
    padrao: float,
    minimo: float | None = None,
    maximo: float | None = None,
) -> float:
    bruto = _texto(form, chave).replace(",", ".")
    if not bruto:
        return padrao
    try:
        valor = float(bruto)
    except ValueError as exc:
        raise ValueError(f"Valor numérico inválido para '{chave}': '{bruto}'.") from exc
    if minimo is not None and valor < minimo:
        raise ValueError(f"O campo '{chave}' deve ser maior ou igual a {minimo}.")
    if maximo is not None and valor > maximo:
        raise ValueError(f"O campo '{chave}' deve ser menor ou igual a {maximo}.")
    return valor


def _extrair_opcoes(form: FormData, settings: Settings) -> OpcoesProcessamento:
    padrao = OpcoesProcessamento.a_partir_de_settings(settings)

    metodo_pdf = _texto(form, "metodo_pdf", padrao.metodo_pdf)
    if metodo_pdf not in ("native_then_ocr", "native"):
        raise ValueError(f"Método de extração de PDF inválido: '{metodo_pdf}'.")

    duracao_min = _decimal(form, "duracao_minima_intervalo", padrao.duracao_minima_intervalo, 1.0)
    duracao_max = _decimal(form, "duracao_maxima_intervalo", padrao.duracao_maxima_intervalo, 1.0)
    if duracao_max < duracao_min:
        raise ValueError(
            "A duração máxima do intervalo explicativo deve ser maior ou igual à duração mínima."
        )

    return OpcoesProcessamento(
        executar_pdf=_flag(form, "executar_pdf"),
        executar_transcricao=_flag(form, "executar_transcricao"),
        executar_alinhamento=_flag(form, "executar_alinhamento"),
        id_documento_existente=_texto(form, "id_documento_existente") or None,
        id_aula_existente=_texto(form, "id_aula_existente") or None,
        metodo_pdf=metodo_pdf,
        modelo_visual=_texto(form, "modelo_visual", padrao.modelo_visual) or padrao.modelo_visual,
        temperatura_visual=_decimal(
            form, "temperatura_visual", padrao.temperatura_visual, 0.0, 2.0
        ),
        seed_visual=_inteiro(form, "seed_visual", padrao.seed_visual, 0),
        pensar_visual=_flag(form, "pensar_visual"),
        titulo_aula=_texto(form, "titulo_aula") or None,
        modelo_whisperx=(
            _texto(form, "modelo_whisperx", padrao.modelo_whisperx) or padrao.modelo_whisperx
        ),
        dispositivo_whisperx=(
            _texto(form, "dispositivo_whisperx", padrao.dispositivo_whisperx)
            or padrao.dispositivo_whisperx
        ),
        tipo_computacao=(
            _texto(form, "tipo_computacao", padrao.tipo_computacao) or padrao.tipo_computacao
        ),
        alinhar_fonemas=_flag(form, "alinhar_fonemas"),
        limiar_silencio=_decimal(form, "limiar_silencio", padrao.limiar_silencio, 0.1),
        duracao_minima_intervalo=duracao_min,
        duracao_maxima_intervalo=duracao_max,
        modo_alinhamento=_texto(form, "modo_alinhamento", padrao.modo_alinhamento),
        estrategia_alinhamento=_texto(
            form, "estrategia_alinhamento", padrao.estrategia_alinhamento
        ),
        estrategia_base=_texto(form, "estrategia_base", padrao.estrategia_base),
        modelo_temporal=_texto(form, "modelo_temporal", padrao.modelo_temporal),
        modelo_embedding=(
            _texto(form, "modelo_embedding", padrao.modelo_embedding) or padrao.modelo_embedding
        ),
        limiar_abstencao=_decimal(form, "limiar_abstencao", padrao.limiar_abstencao, 0.0, 1.0),
        max_paginas=_inteiro(form, "max_paginas", padrao.max_paginas, 1),
        max_unidades=_inteiro(form, "max_unidades", padrao.max_unidades, 1),
        peso_similaridade=_decimal(form, "peso_similaridade", padrao.peso_similaridade, 0.0, 1.0),
        peso_temporal=_decimal(form, "peso_temporal", padrao.peso_temporal, 0.0, 1.0),
        peso_visual=_decimal(form, "peso_visual", padrao.peso_visual, 0.0, 1.0),
        janela_temporal=_inteiro(form, "janela_temporal", padrao.janela_temporal, 0),
        temperatura_hmm=_decimal(form, "temperatura_hmm", padrao.temperatura_hmm, 0.01, 5.0),
    )


async def _salvar_arquivo_se_enviado(
    campo: Any,
    diretorio_uploads: Path,
    extensoes_permitidas: tuple[str, ...],
    rotulo_tipo: str,
) -> Path | None:
    if not isinstance(campo, UploadFile) or not campo.filename or not campo.filename.strip():
        return None

    sufixo = Path(campo.filename).suffix.lower()
    if sufixo not in extensoes_permitidas:
        permitidas = ", ".join(extensoes_permitidas)
        raise ValueError(
            f"Formato inválido para {rotulo_tipo} ('{campo.filename}'). Permitidos: {permitidas}."
        )

    conteudo = await campo.read()
    if not conteudo:
        raise ValueError(f"O arquivo enviado para {rotulo_tipo} ('{campo.filename}') está vazio.")

    return salvar_upload_unico(diretorio_uploads, campo.filename, conteudo)


def _serializar_tarefa(tarefa: TarefaProcessamento) -> JobStatusResponse:
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


def _serializar_vinculo(alinhamento: Alinhamento) -> VinculoIntervaloSchema:
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
    )


def _obter_dimensoes_paginas_pdf(documento: Documento) -> dict[int, tuple[float, float]]:
    dimensoes: dict[int, tuple[float, float]] = {}
    caminho = Path(documento.uri_origem)
    if caminho.is_file():
        try:
            with pymupdf.open(caminho) as pdf:
                for idx, page in enumerate(pdf, start=1):
                    rect = page.rect
                    if rect.width > 0 and rect.height > 0:
                        dimensoes[idx] = (float(rect.width), float(rect.height))
        except Exception:
            dimensoes.clear()

    for pag in documento.paginas:
        if pag.numero_pagina not in dimensoes:
            max_x = max([u.caixa.x1 for u in pag.unidades if u.caixa is not None] + [612.0])
            max_y = max([u.caixa.y1 for u in pag.unidades if u.caixa is not None] + [792.0])
            dimensoes[pag.numero_pagina] = (float(max_x), float(max_y))
    return dimensoes


def _normalizar_caixa(
    x0: float, y0: float, x1: float, y1: float, largura: float, altura: float
) -> CaixaDelimitadoraSchema:
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


def _resolver_aula_para_documento(
    id_documento: str,
    id_aula_param: str | None,
    repo_aula: RepositorioAulaSQLite,
    repo_alin: RepositorioAlinhamentoSQLite,
    gestor: GerenciadorProcessamento,
) -> tuple[Aula | None, list[Alinhamento]]:
    if id_aula_param:
        aula = repo_aula.buscar_por_id(id_aula_param)
        if aula is None:
            raise HTTPException(
                status_code=404,
                detail=f"Aula '{id_aula_param}' não encontrada no banco de dados.",
            )
        alins = repo_alin.listar_por_aula(aula.id_aula, id_documento=id_documento)
        return aula, alins

    aulas = repo_aula.listar()
    melhor_aula: Aula | None = None
    melhores_alins: list[Alinhamento] = []
    for aula in aulas:
        alins = repo_alin.listar_por_aula(aula.id_aula, id_documento=id_documento)
        if alins:
            melhor_aula = aula
            melhores_alins = alins
            break

    if melhor_aula is not None:
        return melhor_aula, melhores_alins

    id_aula_memoria = gestor.obter_aula_associada(id_documento)
    if id_aula_memoria:
        aula_mem = repo_aula.buscar_por_id(id_aula_memoria)
        if aula_mem is not None:
            return aula_mem, []

    if len(aulas) == 1:
        return aulas[0], []

    return None, []


def _parse_range_header(range_header: str, tamanho_total: int) -> tuple[int, int] | None:
    correspondencia = PADRAO_RANGE_BYTES.match(range_header.strip())
    if not correspondencia:
        return None
    inicio_txt, fim_txt = correspondencia.groups()
    if not inicio_txt and not fim_txt:
        return None

    if not inicio_txt:
        sufixo = int(fim_txt)
        if sufixo <= 0:
            return None
        inicio = max(0, tamanho_total - sufixo)
        fim = tamanho_total - 1
    else:
        inicio = int(inicio_txt)
        fim = int(fim_txt) if fim_txt else tamanho_total - 1

    if inicio >= tamanho_total or fim < inicio:
        return None
    fim = min(fim, tamanho_total - 1)
    return inicio, fim


async def _iterar_arquivo_intervalo(
    caminho: Path, inicio: int, fim: int
) -> AsyncIterator[bytes]:
    restante = fim - inicio + 1
    with caminho.open("rb") as arquivo:
        arquivo.seek(inicio)
        while restante > 0:
            bloco = arquivo.read(min(TAMANHO_CHUNK_STREAM, restante))
            if not bloco:
                break
            restante -= len(bloco)
            yield bloco


def _servir_audio_com_range(caminho_audio: Path, range_header: str | None) -> Response:
    if not caminho_audio.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Arquivo de áudio não encontrado no disco: {caminho_audio}",
        )

    tamanho_total = caminho_audio.stat().st_size
    ext = caminho_audio.suffix.lower()
    media_type = (
        EXTENSOES_MIME_AUDIO.get(ext)
        or mimetypes.guess_type(caminho_audio.name)[0]
        or "application/octet-stream"
    )

    if not range_header:
        return StreamingResponse(
            _iterar_arquivo_intervalo(caminho_audio, 0, max(0, tamanho_total - 1)),
            status_code=200,
            media_type=media_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(tamanho_total),
            },
        )

    intervalo = _parse_range_header(range_header, tamanho_total)
    if intervalo is None:
        return Response(
            status_code=416,
            headers={"Content-Range": f"bytes */{tamanho_total}", "Accept-Ranges": "bytes"},
        )

    inicio, fim = intervalo
    tamanho_conteudo = fim - inicio + 1
    return StreamingResponse(
        _iterar_arquivo_intervalo(caminho_audio, inicio, fim),
        status_code=206,
        media_type=media_type,
        headers={
            "Content-Range": f"bytes {inicio}-{fim}/{tamanho_total}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(tamanho_conteudo),
        },
    )


class _StaticFilesLocal(StaticFiles):
    """Serve arquivos estáticos locais garantindo MIME de módulos .mjs e revalidação."""

    async def get_response(self, path: str, scope: Any) -> Response:
        response = await super().get_response(path, scope)
        response.headers.setdefault("Cache-Control", "no-cache")
        if path.endswith(".mjs"):
            response.headers["Content-Type"] = "application/javascript"
        return response


def criar_app(
    settings: Settings | None = None,
    gerenciador: GerenciadorProcessamento | None = None,
) -> FastAPI:
    """Cria a aplicação FastAPI da SPA Offline-First (API REST JSON + estáticos)."""
    cfg = settings or Settings.from_environment()
    gestor = gerenciador or GerenciadorProcessamento(cfg)

    app = FastAPI(title="AnotaAI — API e Interface Web", docs_url=None, redoc_url=None)
    app.mount("/static", _StaticFilesLocal(directory=str(DIRETORIO_STATIC)), name="static")

    @app.get("/")
    async def pagina_principal() -> FileResponse:
        return FileResponse(DIRETORIO_STATIC / "index.html", media_type="text/html")

    @app.get("/api/opcoes-padrao", response_model=OpcoesPadraoResponse)
    async def obter_opcoes_padrao() -> OpcoesPadraoResponse:
        padrao = OpcoesProcessamento.a_partir_de_settings(cfg)
        return OpcoesPadraoResponse(
            executar_pdf=padrao.executar_pdf,
            executar_transcricao=padrao.executar_transcricao,
            executar_alinhamento=padrao.executar_alinhamento,
            metodo_pdf=padrao.metodo_pdf,
            modelo_visual=padrao.modelo_visual,
            temperatura_visual=padrao.temperatura_visual,
            seed_visual=padrao.seed_visual,
            pensar_visual=padrao.pensar_visual,
            modelo_whisperx=padrao.modelo_whisperx,
            dispositivo_whisperx=padrao.dispositivo_whisperx,
            tipo_computacao=padrao.tipo_computacao,
            alinhar_fonemas=padrao.alinhar_fonemas,
            limiar_silencio=padrao.limiar_silencio,
            duracao_minima_intervalo=padrao.duracao_minima_intervalo,
            duracao_maxima_intervalo=padrao.duracao_maxima_intervalo,
            modo_alinhamento=padrao.modo_alinhamento,
            estrategia_alinhamento=padrao.estrategia_alinhamento,
            estrategia_base=padrao.estrategia_base,
            modelo_temporal=padrao.modelo_temporal,
            modelo_embedding=padrao.modelo_embedding,
            limiar_abstencao=padrao.limiar_abstencao,
            max_paginas=padrao.max_paginas,
            max_unidades=padrao.max_unidades,
            peso_similaridade=padrao.peso_similaridade,
            peso_temporal=padrao.peso_temporal,
            peso_visual=padrao.peso_visual,
            janela_temporal=padrao.janela_temporal,
            temperatura_hmm=padrao.temperatura_hmm,
        )

    @app.post("/api/documentos", response_model=JobCriadoResponse, status_code=202)
    async def processar_documentos(request: Request) -> JSONResponse:
        form = await request.form()
        try:
            opcoes = _extrair_opcoes(form, cfg)
            caminho_pdf = await _salvar_arquivo_se_enviado(
                form.get("arquivo_pdf"),
                gestor.diretorio_uploads,
                (".pdf",),
                "PDF",
            )
            caminho_audio = await _salvar_arquivo_se_enviado(
                form.get("arquivo_audio"),
                gestor.diretorio_uploads,
                EXTENSOES_AUDIO_SUPORTADAS,
                "áudio/vídeo",
            )

            if not (
                opcoes.executar_pdf or opcoes.executar_transcricao or opcoes.executar_alinhamento
            ):
                raise ValueError("Selecione pelo menos uma etapa do pipeline para executar.")

            tem_fonte_pdf = (
                (caminho_pdf is not None and opcoes.executar_pdf)
                or opcoes.id_documento_existente is not None
            )
            tem_fonte_audio = (
                (caminho_audio is not None and opcoes.executar_transcricao)
                or opcoes.id_aula_existente is not None
            )
            if not tem_fonte_pdf and not tem_fonte_audio:
                raise ValueError(
                    "Envie um arquivo PDF, um áudio/vídeo ou selecione itens já salvos no acervo."
                )
            if (
                opcoes.executar_alinhamento
                and not (caminho_pdf and opcoes.executar_pdf)
                and not (caminho_audio and opcoes.executar_transcricao)
                and not (opcoes.id_documento_existente and opcoes.id_aula_existente)
            ):
                raise ValueError(
                    "Para alinhar itens do acervo sem novo upload, "
                    "selecione um documento e uma aula."
                )
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"detail": str(exc)})

        tarefa = gestor.iniciar(opcoes, caminho_pdf=caminho_pdf, caminho_audio=caminho_audio)
        payload = JobCriadoResponse(job_id=tarefa.id_job, status=tarefa.status_geral)
        return JSONResponse(status_code=202, content=payload.model_dump())

    @app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
    async def obter_status_job(job_id: str) -> JobStatusResponse:
        tarefa = gestor.obter_tarefa(job_id)
        if tarefa is None:
            raise HTTPException(
                status_code=404,
                detail=f"Tarefa '{job_id}' não encontrada.",
            )
        return _serializar_tarefa(tarefa)

    @app.post("/api/jobs/{job_id}/cancelar", response_model=JobStatusResponse)
    async def cancelar_job(job_id: str) -> JobStatusResponse:
        tarefa = gestor.cancelar(job_id)
        if tarefa is None:
            raise HTTPException(
                status_code=404,
                detail=f"Tarefa '{job_id}' não encontrada.",
            )
        return _serializar_tarefa(tarefa)

    @app.get("/api/documentos", response_model=list[ResumoDocumentoItemSchema])
    async def listar_documentos() -> list[ResumoDocumentoItemSchema]:
        banco_path = Path(cfg.database_path)
        if not banco_path.exists():
            return []

        repo_doc = RepositorioDocumentoSQLite(banco_path)
        repo_aula = RepositorioAulaSQLite(banco_path)
        repo_alin = RepositorioAlinhamentoSQLite(banco_path)

        documentos = repo_doc.listar()
        aulas = repo_aula.listar()
        itens: list[ResumoDocumentoItemSchema] = []

        for doc in documentos:
            aula_associada, alins = _resolver_aula_para_documento(
                doc.id_documento, None, repo_aula, repo_alin, gestor
            )
            itens.append(
                ResumoDocumentoItemSchema(
                    id_documento=doc.id_documento,
                    titulo_documento=doc.titulo,
                    id_aula=aula_associada.id_aula if aula_associada else None,
                    titulo_aula=aula_associada.titulo if aula_associada else None,
                    paginas=len(doc.paginas),
                    unidades=sum(len(p.unidades) for p in doc.paginas),
                    paginas_ocr=sum(1 for p in doc.paginas if p.metodo_extracao == "mixed"),
                    metodo_extracao=doc.proveniencia.metodo_extracao,
                    intervalos=len(aula_associada.intervalos) if aula_associada else 0,
                    alinhamentos=len(alins),
                    tem_audio=bool(
                        aula_associada and Path(aula_associada.caminho_arquivo).is_file()
                    ),
                )
            )
        # Se houver apenas aulas sem documentos, garante que possam ser vistas em /api/aulas
        _ = aulas
        return itens

    @app.get("/api/aulas", response_model=list[ResumoAulaItemSchema])
    async def listar_aulas() -> list[ResumoAulaItemSchema]:
        banco_path = Path(cfg.database_path)
        if not banco_path.exists():
            return []

        repo_aula = RepositorioAulaSQLite(banco_path)
        repo_alin = RepositorioAlinhamentoSQLite(banco_path)
        itens: list[ResumoAulaItemSchema] = []
        for aula in repo_aula.listar():
            alins = repo_alin.listar_por_aula(aula.id_aula)
            itens.append(
                ResumoAulaItemSchema(
                    id_aula=aula.id_aula,
                    titulo=aula.titulo,
                    duracao=aula.metadados.duracao,
                    segmentos=len(aula.segmentos),
                    intervalos=len(aula.intervalos),
                    alinhamentos=len(alins),
                )
            )
        return itens

    @app.get("/api/documentos/{id_documento}", response_model=DocumentoGrafoResponse)
    async def obter_grafo_documento(
        id_documento: str, id_aula: str | None = None
    ) -> DocumentoGrafoResponse:
        banco_path = Path(cfg.database_path)
        if not banco_path.exists():
            raise HTTPException(status_code=404, detail="Banco de dados não inicializado.")

        repo_doc = RepositorioDocumentoSQLite(banco_path)
        repo_aula = RepositorioAulaSQLite(banco_path)
        repo_alin = RepositorioAlinhamentoSQLite(banco_path)

        documento = repo_doc.buscar_por_id(id_documento)
        if documento is None:
            raise HTTPException(
                status_code=404, detail=f"Documento '{id_documento}' não encontrado."
            )

        aula, alinhamentos = _resolver_aula_para_documento(
            id_documento, id_aula, repo_aula, repo_alin, gestor
        )
        dimensoes = _obter_dimensoes_paginas_pdf(documento)

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
                        _normalizar_caixa(
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

        vinculos_serializados = [_serializar_vinculo(a) for a in alinhamentos]
        vinculo_ativo_por_intervalo: dict[str, VinculoIntervaloSchema] = {}
        for v in vinculos_serializados:
            atual = vinculo_ativo_por_intervalo.get(v.id_intervalo)
            if atual is None or (v.manual and not atual.manual):
                vinculo_ativo_por_intervalo[v.id_intervalo] = v

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

    @app.post("/api/documentos/{id_documento}/vinculos", response_model=VinculoIntervaloSchema)
    async def salvar_vinculo_manual(
        id_documento: str, payload: CriarVinculoRequest
    ) -> VinculoIntervaloSchema:
        banco_path = Path(cfg.database_path)
        if not banco_path.exists():
            raise HTTPException(status_code=404, detail="Banco de dados não inicializado.")

        repo_doc = RepositorioDocumentoSQLite(banco_path)
        repo_aula = RepositorioAulaSQLite(banco_path)
        repo_alin = RepositorioAlinhamentoSQLite(banco_path)

        documento = repo_doc.buscar_por_id(id_documento)
        if documento is None:
            raise HTTPException(
                status_code=404, detail=f"Documento '{id_documento}' não encontrado."
            )

        aula, _ = _resolver_aula_para_documento(
            id_documento, payload.id_aula, repo_aula, repo_alin, gestor
        )
        if aula is None:
            raise HTTPException(
                status_code=400,
                detail="Nenhuma aula associada foi encontrada para registrar o vínculo manual.",
            )

        alinhador = AlinharAula(recuperador=None, repositorio_alinhamento=repo_alin)
        try:
            alinhamento = alinhador.registrar_revisao_manual(
                aula=aula,
                documento=documento,
                id_intervalo=payload.id_intervalo,
                ids_paginas=payload.ids_paginas,
                ids_unidades=payload.ids_unidades,
                abster=payload.abster,
                tipo_relacao=payload.tipo_relacao,
                justificativa=payload.justificativa,
            )
        except (ErroIntegridade, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return _serializar_vinculo(alinhamento)

    @app.delete("/api/vinculos/{id_alinhamento}", response_model=VinculoIntervaloSchema)
    async def remover_vinculo(
        id_alinhamento: str,
        id_pagina: str | None = None,
        id_unidade: str | None = None,
    ) -> VinculoIntervaloSchema:
        banco_path = Path(cfg.database_path)
        if not banco_path.exists():
            raise HTTPException(status_code=404, detail="Banco de dados não inicializado.")

        repo_doc = RepositorioDocumentoSQLite(banco_path)
        repo_aula = RepositorioAulaSQLite(banco_path)
        repo_alin = RepositorioAlinhamentoSQLite(banco_path)

        alinhamento = repo_alin.buscar_por_id(id_alinhamento)
        if alinhamento is None:
            raise HTTPException(
                status_code=404, detail=f"Vínculo '{id_alinhamento}' não encontrado."
            )

        documento = repo_doc.buscar_por_id(alinhamento.id_documento)
        aula = repo_aula.buscar_por_id(alinhamento.id_aula)
        if documento is None or aula is None:
            raise HTTPException(
                status_code=404, detail="Documento ou aula do vínculo não encontrados."
            )

        if id_unidade:
            novas_paginas = list(alinhamento.ids_paginas)
            novas_unidades = [u for u in alinhamento.ids_unidades if u != id_unidade]
            abster = not novas_paginas and not novas_unidades
            justificativa = "Unidade removida manualmente na revisão"
        elif id_pagina:
            unidades_da_pagina = {
                u.id_unidade
                for p in documento.paginas
                if p.id_pagina == id_pagina
                for u in p.unidades
            }
            novas_paginas = [p for p in alinhamento.ids_paginas if p != id_pagina]
            novas_unidades = [
                u for u in alinhamento.ids_unidades if u not in unidades_da_pagina
            ]
            abster = not novas_paginas and not novas_unidades
            justificativa = "Página removida manualmente na revisão"
        else:
            novas_paginas = []
            novas_unidades = []
            abster = True
            justificativa = "Vínculo removido manualmente (abstenção explícita)"

        alinhador = AlinharAula(recuperador=None, repositorio_alinhamento=repo_alin)
        try:
            atualizado = alinhador.registrar_revisao_manual(
                aula=aula,
                documento=documento,
                id_intervalo=alinhamento.id_intervalo,
                ids_paginas=novas_paginas,
                ids_unidades=novas_unidades,
                abster=abster,
                tipo_relacao=alinhamento.tipo_relacao or "direct",
                justificativa=justificativa,
            )
        except (ErroIntegridade, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return _serializar_vinculo(atualizado)

    @app.get("/api/documentos/{id_documento}/pdf")
    async def obter_arquivo_pdf(id_documento: str) -> FileResponse:
        banco_path = Path(cfg.database_path)
        if not banco_path.exists():
            raise HTTPException(status_code=404, detail="Banco de dados não inicializado.")

        repo_doc = RepositorioDocumentoSQLite(banco_path)
        documento = repo_doc.buscar_por_id(id_documento)
        if documento is None:
            raise HTTPException(
                status_code=404, detail=f"Documento '{id_documento}' não encontrado."
            )

        caminho_pdf = Path(documento.uri_origem)
        if not caminho_pdf.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"Arquivo PDF original não encontrado no disco: {caminho_pdf}",
            )

        return FileResponse(
            caminho_pdf,
            media_type="application/pdf",
            filename=caminho_pdf.name,
            content_disposition_type="inline",
        )

    @app.get("/api/documentos/{id_documento}/paginas/{numero_pagina}/imagem")
    async def obter_imagem_pagina_pdf(id_documento: str, numero_pagina: int) -> Response:
        banco_path = Path(cfg.database_path)
        if not banco_path.exists():
            raise HTTPException(status_code=404, detail="Banco de dados não inicializado.")

        repo_doc = RepositorioDocumentoSQLite(banco_path)
        documento = repo_doc.buscar_por_id(id_documento)
        if documento is None:
            raise HTTPException(
                status_code=404, detail=f"Documento '{id_documento}' não encontrado."
            )

        caminho_pdf = Path(documento.uri_origem)
        if not caminho_pdf.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"Arquivo PDF original não encontrado no disco: {caminho_pdf}",
            )

        try:
            with pymupdf.open(caminho_pdf) as pdf:
                if numero_pagina < 1 or numero_pagina > len(pdf):
                    raise HTTPException(
                        status_code=404,
                        detail=f"Página {numero_pagina} fora do intervalo do PDF.",
                    )
                pix = pdf[numero_pagina - 1].get_pixmap(dpi=150, alpha=False)
                png_bytes = pix.tobytes("png")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Erro ao renderizar página do PDF: {exc}"
            ) from exc

        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=300"},
        )

    @app.get("/api/documentos/{id_documento}/audio")
    async def obter_arquivo_audio(
        id_documento: str, request: Request, id_aula: str | None = None
    ) -> Response:
        banco_path = Path(cfg.database_path)
        if not banco_path.exists():
            raise HTTPException(status_code=404, detail="Banco de dados não inicializado.")

        repo_doc = RepositorioDocumentoSQLite(banco_path)
        repo_aula = RepositorioAulaSQLite(banco_path)
        repo_alin = RepositorioAlinhamentoSQLite(banco_path)

        if repo_doc.buscar_por_id(id_documento) is None:
            raise HTTPException(
                status_code=404, detail=f"Documento '{id_documento}' não encontrado."
            )

        aula, _ = _resolver_aula_para_documento(
            id_documento, id_aula, repo_aula, repo_alin, gestor
        )
        if aula is None:
            raise HTTPException(
                status_code=404,
                detail="Nenhuma aula com áudio está associada a este documento.",
            )

        return _servir_audio_com_range(
            Path(aula.caminho_arquivo), request.headers.get("range")
        )

    return app
