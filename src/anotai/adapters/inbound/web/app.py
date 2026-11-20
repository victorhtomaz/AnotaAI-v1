from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from anotai.application.ports import RenderizadorDocumento
from anotai.application.use_cases import AlinharAula
from anotai.bootstrap import criar_renderizador_documento
from anotai.config import Settings
from anotai.domain.exceptions import ErroIntegridade

from .gerenciador_processamento import (
    EXTENSOES_AUDIO_SUPORTADAS,
    GerenciadorProcessamento,
    OpcoesProcessamento,
    remover_arquivo_upload_se_orfao,
)
from .parsers import extrair_opcoes, salvar_arquivo_se_enviado
from .schemas import (
    CriarVinculoRequest,
    DocumentoGrafoResponse,
    JobCriadoResponse,
    JobStatusResponse,
    OpcoesPadraoResponse,
    ResumoAulaItemSchema,
    ResumoDocumentoItemSchema,
    VinculoIntervaloSchema,
)
from .serializadores import (
    abrir_repositorios,
    construir_grafo_documento,
    resolver_aula_para_documento,
    serializar_tarefa,
    serializar_vinculo,
)
from .streaming import servir_audio_com_range

DIRETORIO_WEB = Path(__file__).resolve().parent
DIRETORIO_STATIC = DIRETORIO_WEB / "static"

# Garante MIME type válido para módulos ES (.mjs) no Windows (padrão retorna text/plain).
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("application/javascript", ".js")


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
    renderizador: RenderizadorDocumento | None = None,
) -> FastAPI:
    """Cria a aplicação FastAPI da SPA Offline-First (API REST JSON + estáticos)."""
    cfg = settings or Settings.from_environment()
    gestor = gerenciador or GerenciadorProcessamento(cfg)
    renderizador_pdf = renderizador or criar_renderizador_documento()

    app = FastAPI(title="AnotaAI — API e Interface Web", docs_url=None, redoc_url=None)
    app.mount("/static", _StaticFilesLocal(directory=str(DIRETORIO_STATIC)), name="static")

    @app.get("/")
    async def pagina_principal() -> FileResponse:
        return FileResponse(DIRETORIO_STATIC / "index.html", media_type="text/html")

    @app.get("/api/opcoes-padrao", response_model=OpcoesPadraoResponse)
    def obter_opcoes_padrao() -> OpcoesPadraoResponse:
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
            opcoes = extrair_opcoes(form, cfg)
            if not (
                opcoes.executar_pdf or opcoes.executar_transcricao or opcoes.executar_alinhamento
            ):
                raise ValueError("Selecione pelo menos uma etapa do pipeline para executar.")

            caminho_pdf = await salvar_arquivo_se_enviado(
                form.get("arquivo_pdf"),
                gestor.diretorio_uploads,
                (".pdf",),
                "PDF",
                etapa_habilitada=opcoes.executar_pdf,
            )
            caminho_audio = await salvar_arquivo_se_enviado(
                form.get("arquivo_audio"),
                gestor.diretorio_uploads,
                EXTENSOES_AUDIO_SUPORTADAS,
                "áudio/vídeo",
                etapa_habilitada=opcoes.executar_transcricao,
            )

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
    def obter_status_job(job_id: str) -> JobStatusResponse:
        tarefa = gestor.obter_tarefa(job_id)
        if tarefa is None:
            raise HTTPException(
                status_code=404,
                detail=f"Tarefa '{job_id}' não encontrada.",
            )
        return serializar_tarefa(tarefa)

    @app.post("/api/jobs/{job_id}/cancelar", response_model=JobStatusResponse)
    def cancelar_job(job_id: str) -> JobStatusResponse:
        tarefa = gestor.cancelar(job_id)
        if tarefa is None:
            raise HTTPException(
                status_code=404,
                detail=f"Tarefa '{job_id}' não encontrada.",
            )
        return serializar_tarefa(tarefa)

    @app.get("/api/documentos", response_model=list[ResumoDocumentoItemSchema])
    def listar_documentos() -> list[ResumoDocumentoItemSchema]:
        if not Path(cfg.database_path).exists():
            return []

        repo_doc, repo_aula, repo_alin = abrir_repositorios(cfg)
        documentos = repo_doc.listar()
        aulas = repo_aula.listar()
        itens: list[ResumoDocumentoItemSchema] = []

        for doc in documentos:
            aula_associada, alins = resolver_aula_para_documento(
                doc.id_documento,
                None,
                repo_doc,
                repo_aula,
                repo_alin,
                gestor,
                aulas_precarregadas=aulas,
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
        return itens

    @app.get("/api/aulas", response_model=list[ResumoAulaItemSchema])
    def listar_aulas() -> list[ResumoAulaItemSchema]:
        if not Path(cfg.database_path).exists():
            return []

        _, repo_aula, repo_alin = abrir_repositorios(cfg)
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
    def obter_grafo_documento(
        id_documento: str, id_aula: str | None = None
    ) -> DocumentoGrafoResponse:
        repo_doc, repo_aula, repo_alin = abrir_repositorios(cfg)

        documento = repo_doc.buscar_por_id(id_documento)
        if documento is None:
            raise HTTPException(
                status_code=404, detail=f"Documento '{id_documento}' não encontrado."
            )

        aula, alinhamentos = resolver_aula_para_documento(
            id_documento, id_aula, repo_doc, repo_aula, repo_alin, gestor
        )
        return construir_grafo_documento(documento, aula, alinhamentos, renderizador_pdf)

    @app.post("/api/documentos/{id_documento}/vinculos", response_model=VinculoIntervaloSchema)
    def salvar_vinculo_manual(
        id_documento: str, payload: CriarVinculoRequest
    ) -> VinculoIntervaloSchema:
        repo_doc, repo_aula, repo_alin = abrir_repositorios(cfg)

        documento = repo_doc.buscar_por_id(id_documento)
        if documento is None:
            raise HTTPException(
                status_code=404, detail=f"Documento '{id_documento}' não encontrado."
            )

        aula, _ = resolver_aula_para_documento(
            id_documento, payload.id_aula, repo_doc, repo_aula, repo_alin, gestor
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

        mapa_num_pagina = {p.id_pagina: p.numero_pagina for p in documento.paginas}
        return serializar_vinculo(alinhamento, mapa_num_pagina=mapa_num_pagina)

    @app.delete("/api/vinculos/{id_alinhamento}", response_model=VinculoIntervaloSchema)
    def remover_vinculo(
        id_alinhamento: str,
        id_pagina: str | None = None,
        id_unidade: str | None = None,
    ) -> VinculoIntervaloSchema:
        repo_doc, repo_aula, repo_alin = abrir_repositorios(cfg)

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

        alinhador = AlinharAula(recuperador=None, repositorio_alinhamento=repo_alin)
        try:
            atualizado = alinhador.remover_alvo_manual(
                aula=aula,
                documento=documento,
                alinhamento=alinhamento,
                id_pagina=id_pagina,
                id_unidade=id_unidade,
            )
        except (ErroIntegridade, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        mapa_num_pagina = {p.id_pagina: p.numero_pagina for p in documento.paginas}
        return serializar_vinculo(atualizado, mapa_num_pagina=mapa_num_pagina)

    @app.get("/api/documentos/{id_documento}/pdf")
    def obter_arquivo_pdf(id_documento: str) -> FileResponse:
        repo_doc, _, _ = abrir_repositorios(cfg)
        documento = repo_doc.buscar_por_id(id_documento)
        if documento is None:
            raise HTTPException(
                status_code=404, detail=f"Documento '{id_documento}' não encontrado."
            )

        caminho_pdf = Path(documento.uri_origem)
        if not caminho_pdf.is_file():
            raise HTTPException(
                status_code=404,
                detail="Arquivo PDF original não encontrado no disco.",
            )

        return FileResponse(
            caminho_pdf,
            media_type="application/pdf",
            filename=caminho_pdf.name,
            content_disposition_type="inline",
        )

    @app.get("/api/documentos/{id_documento}/paginas/{numero_pagina}/imagem")
    def obter_imagem_pagina_pdf(id_documento: str, numero_pagina: int) -> Response:
        repo_doc, _, _ = abrir_repositorios(cfg)
        documento = repo_doc.buscar_por_id(id_documento)
        if documento is None:
            raise HTTPException(
                status_code=404, detail=f"Documento '{id_documento}' não encontrado."
            )

        caminho_pdf = Path(documento.uri_origem)
        if not caminho_pdf.is_file():
            raise HTTPException(
                status_code=404,
                detail="Arquivo PDF original não encontrado no disco.",
            )

        try:
            png_bytes = renderizador_pdf.renderizar_pagina_png(caminho_pdf, numero_pagina, dpi=150)
        except IndexError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
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
    def obter_arquivo_audio(
        id_documento: str, request: Request, id_aula: str | None = None
    ) -> Response:
        repo_doc, repo_aula, repo_alin = abrir_repositorios(cfg)

        if repo_doc.buscar_por_id(id_documento) is None:
            raise HTTPException(
                status_code=404, detail=f"Documento '{id_documento}' não encontrado."
            )

        aula, _ = resolver_aula_para_documento(
            id_documento, id_aula, repo_doc, repo_aula, repo_alin, gestor
        )
        if aula is None:
            raise HTTPException(
                status_code=404,
                detail="Nenhuma aula com áudio está associada a este documento.",
            )

        return servir_audio_com_range(
            Path(aula.caminho_arquivo), request.headers.get("range")
        )

    @app.delete("/api/documentos/{id_documento}")
    def excluir_documento(id_documento: str) -> dict[str, Any]:
        repo_doc, _, _ = abrir_repositorios(cfg)
        documento = repo_doc.buscar_por_id(id_documento)
        if documento is None:
            raise HTTPException(
                status_code=404, detail=f"Documento '{id_documento}' não encontrado."
            )

        repo_doc.excluir(id_documento)
        gestor.remover_vinculo_documento(id_documento)
        caminhos_em_uso = {Path(d.uri_origem).resolve() for d in repo_doc.listar()}
        remover_arquivo_upload_se_orfao(
            Path(documento.uri_origem), gestor.diretorio_uploads, caminhos_em_uso
        )
        return {"ok": True, "id_documento": id_documento}

    @app.delete("/api/aulas/{id_aula}")
    def excluir_aula(id_aula: str) -> dict[str, Any]:
        _, repo_aula, _ = abrir_repositorios(cfg)
        aula = repo_aula.buscar_por_id(id_aula)
        if aula is None:
            raise HTTPException(
                status_code=404, detail=f"Aula '{id_aula}' não encontrada."
            )

        repo_aula.excluir(id_aula)
        gestor.remover_vinculo_aula(id_aula)
        caminhos_em_uso = {Path(a.caminho_arquivo).resolve() for a in repo_aula.listar()}
        remover_arquivo_upload_se_orfao(
            Path(aula.caminho_arquivo), gestor.diretorio_uploads, caminhos_em_uso
        )
        (Path(cfg.raw_transcripts_directory) / f"{id_aula}.json").unlink(missing_ok=True)
        return {"ok": True, "id_aula": id_aula}

    return app
