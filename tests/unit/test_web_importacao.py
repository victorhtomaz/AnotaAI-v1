import mimetypes
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import anyio
import anyio.to_thread
import httpx

from anotai.adapters.inbound.cli.comando_web import executar_comando_web
from anotai.adapters.inbound.cli.principal import criar_parser
from anotai.adapters.inbound.web import GerenciadorProcessamento, criar_app
from anotai.adapters.inbound.web.app import DIRETORIO_STATIC
from anotai.adapters.outbound.persistence import (
    RepositorioAlinhamentoSQLite,
    RepositorioAulaSQLite,
    RepositorioDocumentoSQLite,
)
from anotai.config import Settings
from anotai.domain.entities import (
    Alinhamento,
    Aula,
    Documento,
    IntervaloExplicativo,
    PaginaDocumento,
    SegmentoTranscricao,
    UnidadeDocumento,
)
from anotai.domain.value_objects import (
    CaixaDelimitadora,
    IntervaloTempo,
    MetadadosAudio,
    ProvenienciaDocumento,
    ResultadoAlinhamentoIntervalo,
)


class _ArquivoAsyncFake:
    def __init__(self, caminho: Path, modo: str = "rb") -> None:
        self._arquivo = caminho.open(modo)

    async def read(self, tamanho: int = -1) -> bytes:
        return self._arquivo.read(tamanho)

    async def aclose(self) -> None:
        self._arquivo.close()


async def _open_file_inline(caminho: Any, mode: str = "rb", **kwargs: Any) -> _ArquivoAsyncFake:
    return _ArquivoAsyncFake(Path(caminho), mode)


class _CancelScopeNoop:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> "_CancelScopeNoop":
        return self

    def __exit__(self, *args: Any) -> bool:
        return False


async def _run_sync_inline(func: Any, *args: Any, **kwargs: Any) -> Any:
    return func(*args)


def _executar_corrotina_sem_loop(coro: Any) -> Any:
    """Executa uma corrotina ASGI pura sem criar event loop com socketpair."""
    with (
        patch.object(anyio.to_thread, "run_sync", _run_sync_inline),
        patch.object(anyio, "open_file", _open_file_inline),
        patch.object(anyio, "CancelScope", _CancelScopeNoop),
    ):
        try:
            while True:
                coro.send(None)
        except StopIteration as stop:
            return stop.value


class _WrapperASGISpec24:
    """Define spec_version 2.4 no scope ASGI para FileResponse rodar sem task group."""

    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        asgi_info = dict(scope.get("asgi") or {})
        asgi_info.setdefault("spec_version", "2.4")
        scope["asgi"] = asgi_info
        await self._app(scope, receive, send)


class ClienteTesteASGI:
    """Cliente síncrono sobre httpx.ASGITransport para testes sem sockets no sandbox."""

    def __init__(self, app: Any) -> None:
        self._app = _WrapperASGISpec24(app)

    def _requisitar(self, metodo: str, url: str, **kwargs: Any) -> httpx.Response:
        async def _executar() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self._app),
                base_url="http://testserver",
            ) as cliente:
                return await cliente.request(metodo, url, **kwargs)

        return _executar_corrotina_sem_loop(_executar())

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._requisitar("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._requisitar("POST", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._requisitar("DELETE", url, **kwargs)


def _settings_isoladas(tmp_path: Path) -> Settings:
    processados = tmp_path / "processados"
    return Settings(
        processed_directory=str(processados),
        database_path=str(processados / "anotai.sqlite"),
        raw_transcripts_directory=str(processados / "transcricoes_brutas"),
    )


def _documento_ficticio(caminho_pdf: Path) -> Documento:
    return Documento(
        id_documento="doc-web-1",
        uri_origem=str(caminho_pdf),
        titulo="Material Web",
        paginas=[
            PaginaDocumento(
                id_pagina="doc-web-1-p1",
                numero_pagina=1,
                texto_nativo="Conteúdo da página 1",
                texto_normalizado="Conteúdo da página 1",
                metodo_extracao="mixed",
                unidades=[
                    UnidadeDocumento(
                        id_unidade="doc-web-1-p1-u1",
                        id_documento="doc-web-1",
                        id_pagina="doc-web-1-p1",
                        tipo="paragraph",
                        texto="Parágrafo introdutório sobre redes neurais.",
                        ordem_leitura=1,
                        caixa=CaixaDelimitadora(60.0, 80.0, 360.0, 160.0),
                        fonte="native",
                    ),
                    UnidadeDocumento(
                        id_unidade="doc-web-1-p1-u2",
                        id_documento="doc-web-1",
                        id_pagina="doc-web-1-p1",
                        tipo="figure",
                        texto="Diagrama extraído por OCR",
                        ordem_leitura=2,
                        caixa=CaixaDelimitadora(60.0, 200.0, 460.0, 400.0),
                        fonte="ollama",
                    ),
                ],
            ),
            PaginaDocumento(
                id_pagina="doc-web-1-p2",
                numero_pagina=2,
                texto_nativo="Conteúdo da página 2",
                texto_normalizado="Conteúdo da página 2",
                metodo_extracao="native",
                unidades=[
                    UnidadeDocumento(
                        id_unidade="doc-web-1-p2-u1",
                        id_documento="doc-web-1",
                        id_pagina="doc-web-1-p2",
                        tipo="title",
                        texto="Backpropagation",
                        ordem_leitura=1,
                        caixa=CaixaDelimitadora(50.0, 50.0, 300.0, 90.0),
                        fonte="native",
                    )
                ],
            ),
        ],
        versao_processamento="v1",
        proveniencia=ProvenienciaDocumento(
            uri_origem=str(caminho_pdf),
            metodo_extracao="native_then_ocr",
            versao_pipeline="v1",
            modelo="qwen3-vl:8b",
        ),
    )


def _aula_ficticia(caminho_audio: Path) -> Aula:
    return Aula(
        id_aula="aula-web-1",
        titulo="Aula Web Teste",
        uri_origem=str(caminho_audio),
        caminho_arquivo=caminho_audio,
        metadados=MetadadosAudio(duracao=25.0, taxa_amostragem=16000, canais=1, formato="wav"),
        segmentos=[
            SegmentoTranscricao(
                id_segmento="seg-1",
                id_aula="aula-web-1",
                texto="Explicação sobre redes neurais.",
                intervalo=IntervaloTempo(0.0, 12.0),
                ordem=1,
            ),
            SegmentoTranscricao(
                id_segmento="seg-2",
                id_aula="aula-web-1",
                texto="Comentário fora do material.",
                intervalo=IntervaloTempo(12.0, 24.0),
                ordem=2,
            ),
        ],
        intervalos=[
            IntervaloExplicativo(
                id_intervalo="int-1",
                id_aula="aula-web-1",
                texto="Explicação sobre redes neurais.",
                intervalo=IntervaloTempo(0.0, 12.0),
                ordem=1,
                ids_segmentos=["seg-1"],
            ),
            IntervaloExplicativo(
                id_intervalo="int-2",
                id_aula="aula-web-1",
                texto="Comentário fora do material.",
                intervalo=IntervaloTempo(12.0, 24.0),
                ordem=2,
                ids_segmentos=["seg-2"],
            ),
        ],
        idioma="pt",
    )


def test_spa_index_assets_locais_e_opcoes_padrao(tmp_path: Path) -> None:
    cfg = _settings_isoladas(tmp_path)
    app = criar_app(settings=cfg)
    client = ClienteTesteASGI(app)

    resp_index = client.get("/")
    assert resp_index.status_code == 200
    assert "text/html" in resp_index.headers["content-type"]

    html = resp_index.text
    assert "x-data" in html
    assert "$store.anotai" in html
    assert "@timeupdate" in html
    assert "/static/vendor/alpine.min.js" in html
    assert "/static/js/app.js" in html
    assert "/static/css/styles.css" in html
    assert "htmx" not in html.lower()
    assert "https://" not in html
    assert 'name="dispositivo_whisperx"' in html
    assert 'name="limiar_silencio"' in html
    assert 'name="modo_alinhamento"' in html
    assert "Interromper processamento" in html
    for campo_oculto in (
        'name="modelo_visual"',
        'name="temperatura_visual"',
        'name="modelo_whisperx"',
        'name="modelo_embedding"',
        'name="temperatura_hmm"',
    ):
        assert campo_oculto not in html

    for arquivo in (
        DIRETORIO_STATIC / "vendor" / "alpine.min.js",
        DIRETORIO_STATIC / "vendor" / "pdf.min.mjs",
        DIRETORIO_STATIC / "vendor" / "pdf.worker.min.mjs",
        DIRETORIO_STATIC / "js" / "pdf-viewer.js",
        DIRETORIO_STATIC / "js" / "app.js",
        DIRETORIO_STATIC / "css" / "styles.css",
    ):
        assert arquivo.is_file(), f"Arquivo estático ausente: {arquivo}"

    css_texto = (DIRETORIO_STATIC / "css" / "styles.css").read_text(encoding="utf-8").lower()
    assert "#1f5e63" in css_texto
    assert "#e8e6df" in css_texto
    assert mimetypes.guess_type("pdf.min.mjs")[0] in (
        "application/javascript",
        "text/javascript",
    )

    resp_opcoes = client.get("/api/opcoes-padrao")
    assert resp_opcoes.status_code == 200
    dados_opcoes = resp_opcoes.json()
    assert dados_opcoes["modelo_visual"] == cfg.visual_model
    assert dados_opcoes["modelo_whisperx"] == cfg.whisperx_model
    assert dados_opcoes["metodo_pdf"] == "native_then_ocr"
    assert dados_opcoes["estrategia_base"] == "hybrid"
    assert dados_opcoes["modelo_temporal"] == "hmm"
    assert "modo_alinhamento === 'personalizado'" in html
    assert 'x-show="$store.anotai.opcoes.executar_pdf"' in html
    assert 'x-show="$store.anotai.opcoes.executar_transcricao"' in html
    assert 'x-show="$store.anotai.opcoes.executar_alinhamento"' in html
    assert "$store.anotai.documentosVinculados" in html
    assert "$store.anotai.opcoesAlinhamentoDisponiveis" in html
    assert 'value="hierarchical_hmm"' not in html
    assert 'value="temporal_hmm"' not in html
    assert "GPU CUDA" in html
    for termo_tecnico in ("Ollama", "WhisperX", "BM25", "HMM", "Kernel", "ASR"):
        assert termo_tecnico not in html


def test_post_documentos_e_polling_status_job_json(tmp_path: Path) -> None:
    cfg = _settings_isoladas(tmp_path)
    chamadas: dict[str, object] = {}

    class FakeImportarDoc:
        def __init__(self, extrator: Any, repositorio: Any = None) -> None:
            self.extrator = extrator

        def executar(self, caminho: Path, metodo: str) -> Documento:
            chamadas["pdf"] = (caminho, metodo)
            return _documento_ficticio(caminho)

    class FakeTranscrever:
        def __init__(
            self,
            inspetor: Any,
            provedor: Any,
            repositorio: Any = None,
            agrupador: Any = None,
            diretorio_bruto: Any = None,
        ) -> None:
            chamadas["whisperx"] = (provedor.modelo, provedor.dispositivo_solicitado)

        def executar(self, caminho: Path, titulo: str | None = None) -> Aula:
            chamadas["audio"] = (caminho, titulo)
            return _aula_ficticia(caminho)

    class FakeAlinhar:
        def __init__(
            self,
            recuperador: Any,
            repositorio_alinhamento: Any = None,
            estrategia: str = "hierarchical",
            modelo_temporal: str = "kernel",
            **kwargs: Any,
        ) -> None:
            chamadas["alinhar"] = (estrategia, modelo_temporal, kwargs.get("limiar_abstencao"))

        def executar(self, aula: Aula, documento: Documento) -> list[ResultadoAlinhamentoIntervalo]:
            alin = Alinhamento(
                id_alinhamento="align-1",
                id_aula=aula.id_aula,
                id_documento=documento.id_documento,
                id_intervalo=aula.intervalos[0].id_intervalo,
                ids_paginas=[documento.paginas[0].id_pagina],
                ids_unidades=[documento.paginas[0].unidades[0].id_unidade],
                status="aligned",
                tipo_relacao="direct",
                confianca=0.88,
                estrategia="hierarchical_hmm",
            )
            return [
                ResultadoAlinhamentoIntervalo(
                    alinhamento=alin,
                    ordem_intervalo=1,
                    texto_intervalo=aula.intervalos[0].texto,
                    intervalo_tempo=aula.intervalos[0].intervalo,
                )
            ]

    repo_alin_mock = MagicMock()
    gestor = GerenciadorProcessamento(
        settings=cfg,
        executar_sincrono=True,
        repo_doc_cls=lambda _: MagicMock(),
        repo_aula_cls=lambda _: MagicMock(),
        repo_alin_cls=lambda _: repo_alin_mock,
        importar_doc_cls=FakeImportarDoc,
        transcrever_cls=FakeTranscrever,
        alinhar_cls=FakeAlinhar,
        recuperador_cls=lambda **kwargs: MagicMock(),
        extrator_pdf_cls=lambda analisador: analisador,
        analisador_visual_cls=lambda *args, **kwargs: MagicMock(),
        inspetor_audio_cls=lambda: MagicMock(),
        provedor_whisperx_cls=lambda **kwargs: SimpleNamespace(
            modelo=kwargs["modelo"], dispositivo_solicitado=kwargs["dispositivo"]
        ),
        indices_builder=lambda *args, **kwargs: (MagicMock(), MagicMock()),
    )
    app = criar_app(settings=cfg, gerenciador=gestor)
    client = ClienteTesteASGI(app)

    resp_invalido = client.post(
        "/api/documentos",
        data={"executar_pdf": "on", "executar_transcricao": "on", "executar_alinhamento": "on"},
    )
    assert resp_invalido.status_code == 400
    assert "detail" in resp_invalido.json()

    resp = client.post(
        "/api/documentos",
        files={
            "arquivo_pdf": ("slides.pdf", b"%PDF-1.4 mock", "application/pdf"),
            "arquivo_audio": ("aula.wav", b"RIFF mock", "audio/wav"),
        },
        data={
            "executar_pdf": "on",
            "executar_transcricao": "on",
            "executar_alinhamento": "on",
            "metodo_pdf": "native_then_ocr",
            "modelo_visual": "qwen3-vl:8b",
            "titulo_aula": "Aula 01",
            "modelo_whisperx": "medium",
            "dispositivo_whisperx": "cpu",
            "tipo_computacao": "int8",
            "modo_alinhamento": "padrao",
            "limiar_abstencao": "0.1",
        },
    )

    assert resp.status_code == 202
    assert "application/json" in resp.headers["content-type"]
    criado = resp.json()
    assert criado["job_id"].startswith("job-")

    resp_job = client.get(f"/api/jobs/{criado['job_id']}")
    assert resp_job.status_code == 200
    status_job = resp_job.json()
    assert status_job["status_geral"] == "concluido"
    assert status_job["em_andamento"] is False
    assert status_job["id_documento"] == "doc-web-1"
    assert status_job["id_aula"] == "aula-web-1"
    assert status_job["etapas"]["pdf"]["estado"] == "concluido"
    assert status_job["etapas"]["ocr"]["estado"] == "concluido"
    assert status_job["etapas"]["transcricao"]["estado"] == "concluido"
    assert status_job["etapas"]["alinhamento"]["estado"] == "concluido"
    assert status_job["etapas"]["alinhamento"]["metricas"]["Alinhados"] == "1/1"

    assert chamadas["pdf"][1] == "native_then_ocr"
    assert chamadas["whisperx"] == ("medium", "cpu")
    assert chamadas["alinhar"] == ("hierarchical", "hmm", 0.1)
    assert repo_alin_mock.salvar_lote.call_count == 1
    salvos = repo_alin_mock.salvar_lote.call_args[0][0]
    assert salvos[0].estrategia == "hierarchical_hmm+hybrid"

    assert client.get("/api/jobs/job-inexistente").status_code == 404


def test_grafo_documento_e_revisao_manual_json(tmp_path: Path) -> None:
    cfg = _settings_isoladas(tmp_path)
    banco = Path(cfg.database_path)
    pdf_path = tmp_path / "aula.pdf"
    audio_path = tmp_path / "aula.wav"
    pdf_path.write_bytes(b"%PDF-1.4\nconteudo")
    audio_path.write_bytes(b"0123456789ABCDEF")

    doc = _documento_ficticio(pdf_path)
    aula = _aula_ficticia(audio_path)

    repo_doc = RepositorioDocumentoSQLite(banco)
    repo_aula = RepositorioAulaSQLite(banco)
    repo_alin = RepositorioAlinhamentoSQLite(banco)
    repo_doc.salvar(doc)
    repo_aula.salvar(aula)

    alin_auto = Alinhamento(
        id_alinhamento=Alinhamento.gerar_id_estavel("int-1", doc.id_documento, "hierarchical"),
        id_aula=aula.id_aula,
        id_documento=doc.id_documento,
        id_intervalo="int-1",
        ids_paginas=["doc-web-1-p1", "doc-web-1-p2"],
        ids_unidades=["doc-web-1-p1-u1", "doc-web-1-p2-u1"],
        status="aligned",
        tipo_relacao="direct",
        confianca=0.81,
        estrategia="hierarchical",
        origem="automatic",
    )
    alin_abs = Alinhamento(
        id_alinhamento=Alinhamento.gerar_id_estavel("int-2", doc.id_documento, "hierarchical"),
        id_aula=aula.id_aula,
        id_documento=doc.id_documento,
        id_intervalo="int-2",
        ids_paginas=[],
        ids_unidades=[],
        status="abstained",
        tipo_relacao=None,
        confianca=0.1,
        estrategia="hierarchical",
        justificativa="Sem evidência documental suficiente",
        origem="automatic",
    )
    repo_alin.salvar_lote([alin_auto, alin_abs])

    app = criar_app(settings=cfg)
    client = ClienteTesteASGI(app)

    resp_lista = client.get("/api/documentos")
    assert resp_lista.status_code == 200
    lista = resp_lista.json()
    assert len(lista) == 1
    assert lista[0]["id_documento"] == "doc-web-1"
    assert lista[0]["paginas"] == 2
    assert lista[0]["alinhamentos"] == 2

    resp_grafo = client.get("/api/documentos/doc-web-1")
    assert resp_grafo.status_code == 200
    grafo = resp_grafo.json()
    assert grafo["id_aula"] == "aula-web-1"
    assert len(grafo["paginas"]) == 2
    caixa_u1 = grafo["paginas"][0]["unidades"][0]["caixa"]
    assert caixa_u1 is not None
    assert 0.0 <= caixa_u1["x_pct"] <= 100.0
    assert caixa_u1["w_pct"] > 0.0

    inter1, inter2 = grafo["intervalos"]
    assert inter1["vinculo"]["automatico"] is True
    assert inter1["vinculo"]["manual"] is False
    assert inter1["vinculo"]["ids_paginas"] == ["doc-web-1-p1", "doc-web-1-p2"]
    assert inter2["vinculo"]["abstido"] is True

    # Revisão manual criando vínculo multi-rótulo
    resp_post_vinc = client.post(
        "/api/documentos/doc-web-1/vinculos",
        json={
            "id_intervalo": "int-1",
            "ids_paginas": ["doc-web-1-p1", "doc-web-1-p2"],
            "ids_unidades": ["doc-web-1-p1-u2", "doc-web-1-p2-u1"],
            "abster": False,
            "tipo_relacao": "reference",
            "justificativa": "Confirmado na revisão manual",
        },
    )
    assert resp_post_vinc.status_code == 200
    vinc_manual = resp_post_vinc.json()
    assert vinc_manual["manual"] is True
    assert vinc_manual["automatico"] is False
    assert vinc_manual["tipo_relacao"] == "reference"

    # Grafo agora prioriza o vínculo manual para int-1
    grafo_atualizado = client.get("/api/documentos/doc-web-1").json()
    assert grafo_atualizado["intervalos"][0]["vinculo"]["manual"] is True
    assert grafo_atualizado["intervalos"][0]["vinculo"]["ids_unidades"] == [
        "doc-web-1-p1-u2",
        "doc-web-1-p2-u1",
    ]

    # Remoção parcial de unidade
    resp_del_unid = client.delete(
        f"/api/vinculos/{vinc_manual['id_alinhamento']}?id_unidade=doc-web-1-p1-u2"
    )
    assert resp_del_unid.status_code == 200
    assert resp_del_unid.json()["ids_unidades"] == ["doc-web-1-p2-u1"]
    assert resp_del_unid.json()["abstido"] is False

    # Remoção total marca abstenção explícita ∅
    resp_del_total = client.delete(f"/api/vinculos/{vinc_manual['id_alinhamento']}")
    assert resp_del_total.status_code == 200
    assert resp_del_total.json()["abstido"] is True
    assert resp_del_total.json()["manual"] is True


def test_entrega_pdf_e_streaming_audio_com_range_206(tmp_path: Path) -> None:
    import pymupdf

    cfg = _settings_isoladas(tmp_path)
    banco = Path(cfg.database_path)
    pdf_path = tmp_path / "slides.pdf"
    audio_path = tmp_path / "aula.wav"

    doc_fitz = pymupdf.open()
    pag_fitz = doc_fitz.new_page(width=612, height=792)
    pag_fitz.insert_text((72, 100), "Conteudo de teste")
    doc_fitz.save(pdf_path)
    doc_fitz.close()

    pdf_bytes = pdf_path.read_bytes()
    audio_bytes = b"0123456789ABCDEF"
    audio_path.write_bytes(audio_bytes)

    doc = _documento_ficticio(pdf_path)
    aula = _aula_ficticia(audio_path)

    RepositorioDocumentoSQLite(banco).salvar(doc)
    RepositorioAulaSQLite(banco).salvar(aula)

    app = criar_app(settings=cfg)
    client = ClienteTesteASGI(app)

    resp_pdf = client.get("/api/documentos/doc-web-1/pdf")
    assert resp_pdf.status_code == 200
    assert "application/pdf" in resp_pdf.headers["content-type"]
    assert resp_pdf.content == pdf_bytes

    resp_img = client.get("/api/documentos/doc-web-1/paginas/1/imagem")
    assert resp_img.status_code == 200
    assert resp_img.headers["content-type"] == "image/png"
    assert resp_img.content.startswith(b"\x89PNG")

    resp_audio_full = client.get("/api/documentos/doc-web-1/audio")
    assert resp_audio_full.status_code == 200
    assert resp_audio_full.headers["accept-ranges"] == "bytes"
    assert resp_audio_full.content == audio_bytes

    resp_range = client.get(
        "/api/documentos/doc-web-1/audio",
        headers={"Range": "bytes=2-7"},
    )
    assert resp_range.status_code == 206
    assert resp_range.headers["accept-ranges"] == "bytes"
    assert resp_range.headers["content-range"] == "bytes 2-7/16"
    assert resp_range.headers["content-length"] == "6"
    assert resp_range.content == b"234567"

    resp_invalido = client.get(
        "/api/documentos/doc-web-1/audio",
        headers={"Range": "bytes=99-120"},
    )
    assert resp_invalido.status_code == 416


def test_cli_subcomando_web_registrado() -> None:
    parser = criar_parser()
    args = parser.parse_args(["web", "--host", "0.0.0.0", "--port", "8080"])
    assert args.subcomando == "web"
    assert args.host == "0.0.0.0"
    assert args.port == 8080

    runner_mock = MagicMock()
    codigo = executar_comando_web(
        args,
        Settings(),
        app_factory=lambda settings: "app-falsa",
        runner=runner_mock,
    )
    assert codigo == 0
    runner_mock.assert_called_once_with("app-falsa", host="0.0.0.0", port=8080)


def test_cancelar_processamento_interrompe_etapas_subsequentes(tmp_path: Path) -> None:
    import threading

    cfg = _settings_isoladas(tmp_path)
    etapa_iniciada = threading.Event()
    liberar_etapa = threading.Event()
    transcricao_chamada = threading.Event()

    class FakeImportarLento:
        def __init__(self, extrator: Any, repositorio: Any = None) -> None:
            pass

        def executar(self, caminho: Path, metodo: str) -> Documento:
            etapa_iniciada.set()
            liberar_etapa.wait(timeout=2.0)
            return _documento_ficticio(caminho)

    class FakeTranscreverNaoExecutado:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def executar(self, caminho: Path, titulo: str | None = None) -> Aula:
            transcricao_chamada.set()
            return _aula_ficticia(caminho)

    gestor = GerenciadorProcessamento(
        settings=cfg,
        executar_sincrono=False,
        repo_doc_cls=lambda _: MagicMock(),
        repo_aula_cls=lambda _: MagicMock(),
        repo_alin_cls=lambda _: MagicMock(),
        importar_doc_cls=FakeImportarLento,
        transcrever_cls=FakeTranscreverNaoExecutado,
        extrator_pdf_cls=lambda analisador: analisador,
        analisador_visual_cls=lambda *args, **kwargs: MagicMock(),
    )
    app = criar_app(settings=cfg, gerenciador=gestor)
    client = ClienteTesteASGI(app)

    resp = client.post(
        "/api/documentos",
        files={
            "arquivo_pdf": ("slides.pdf", b"%PDF-1.4 mock", "application/pdf"),
            "arquivo_audio": ("aula.wav", b"RIFF mock", "audio/wav"),
        },
        data={"executar_pdf": "on", "executar_transcricao": "on", "executar_alinhamento": "on"},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    assert etapa_iniciada.wait(timeout=2.0)
    resp_cancel = client.post(f"/api/jobs/{job_id}/cancelar")
    assert resp_cancel.status_code == 200
    dados = resp_cancel.json()
    assert dados["status_geral"] == "cancelado"
    assert dados["em_andamento"] is False
    assert dados["etapas"]["pdf"]["estado"] == "cancelado"
    assert dados["etapas"]["transcricao"]["estado"] == "ignorado"
    assert dados["etapas"]["alinhamento"]["estado"] == "ignorado"

    liberar_etapa.set()
    gestor._executor.shutdown(wait=True)
    assert not transcricao_chamada.is_set()
    assert not list(gestor.diretorio_uploads.glob("*"))
    assert client.post("/api/jobs/job-inexistente/cancelar").status_code == 404


def test_excluir_documento_e_aula_remove_banco_e_uploads(tmp_path: Path) -> None:
    cfg = _settings_isoladas(tmp_path)
    banco = Path(cfg.database_path)
    gestor = GerenciadorProcessamento(settings=cfg)
    gestor.diretorio_uploads.mkdir(parents=True, exist_ok=True)

    pdf_upload = gestor.diretorio_uploads / "slides_del.pdf"
    audio_upload = gestor.diretorio_uploads / "aula_del.wav"
    pdf_upload.write_bytes(b"%PDF-1.4")
    audio_upload.write_bytes(b"RIFF")

    doc = _documento_ficticio(pdf_upload)
    aula = _aula_ficticia(audio_upload)

    repo_doc = RepositorioDocumentoSQLite(banco)
    repo_aula = RepositorioAulaSQLite(banco)
    repo_doc.salvar(doc)
    repo_aula.salvar(aula)

    bruto_dir = Path(cfg.raw_transcripts_directory)
    bruto_dir.mkdir(parents=True, exist_ok=True)
    bruto_json = bruto_dir / f"{aula.id_aula}.json"
    bruto_json.write_text("{}", encoding="utf-8")

    app = criar_app(settings=cfg, gerenciador=gestor)
    client = ClienteTesteASGI(app)

    resp_del_doc = client.delete(f"/api/documentos/{doc.id_documento}")
    assert resp_del_doc.status_code == 200
    assert resp_del_doc.json() == {"ok": True, "id_documento": doc.id_documento}
    assert repo_doc.buscar_por_id(doc.id_documento) is None
    assert not pdf_upload.exists()
    assert client.delete(f"/api/documentos/{doc.id_documento}").status_code == 404

    resp_del_aula = client.delete(f"/api/aulas/{aula.id_aula}")
    assert resp_del_aula.status_code == 200
    assert resp_del_aula.json() == {"ok": True, "id_aula": aula.id_aula}
    assert repo_aula.buscar_por_id(aula.id_aula) is None
    assert not audio_upload.exists()
    assert not bruto_json.exists()
    assert client.delete(f"/api/aulas/{aula.id_aula}").status_code == 404


def test_limiar_abstencao_padrao_hmm_e_sem_hmm(tmp_path: Path) -> None:
    cfg = _settings_isoladas(tmp_path)
    pdf_path = tmp_path / "aula.pdf"
    audio_path = tmp_path / "aula.wav"
    pdf_path.write_bytes(b"%PDF-1.4")
    audio_path.write_bytes(b"RIFF")

    doc = _documento_ficticio(pdf_path)
    aula = _aula_ficticia(audio_path)
    limiares_capturados: list[float] = []

    class FakeAlinharCaptura:
        def __init__(self, **kwargs: Any) -> None:
            limiares_capturados.append(kwargs["limiar_abstencao"])

        def executar(self, aula_arg: Aula, doc_arg: Documento) -> list[Any]:
            return []

    repo_doc_mock = MagicMock()
    repo_doc_mock.buscar_por_id.return_value = doc
    repo_aula_mock = MagicMock()
    repo_aula_mock.buscar_por_id.return_value = aula

    gestor = GerenciadorProcessamento(
        settings=cfg,
        executar_sincrono=True,
        repo_doc_cls=lambda _: repo_doc_mock,
        repo_aula_cls=lambda _: repo_aula_mock,
        repo_alin_cls=lambda _: MagicMock(),
        alinhar_cls=FakeAlinharCaptura,
        recuperador_cls=lambda **kwargs: MagicMock(),
        indices_builder=lambda *args, **kwargs: (MagicMock(), MagicMock()),
    )
    app = criar_app(settings=cfg, gerenciador=gestor)
    client = ClienteTesteASGI(app)

    resp_hmm = client.post(
        "/api/documentos",
        data={
            "executar_alinhamento": "on",
            "id_documento_existente": doc.id_documento,
            "id_aula_existente": aula.id_aula,
            "modo_alinhamento": "padrao",
        },
    )
    assert resp_hmm.status_code == 202

    resp_sem_hmm = client.post(
        "/api/documentos",
        data={
            "executar_alinhamento": "on",
            "id_documento_existente": doc.id_documento,
            "id_aula_existente": aula.id_aula,
            "modo_alinhamento": "rapido",
        },
    )
    assert resp_sem_hmm.status_code == 202

    assert limiares_capturados == [0.15, 0.25]


def test_modulos_js_e_contratos_frontend_presentes(tmp_path: Path) -> None:
    from anotai.adapters.inbound.web.gerenciador_processamento import (
        OpcoesProcessamento,
        resolver_configuracao_alinhamento,
    )

    cfg = _settings_isoladas(tmp_path)
    app = criar_app(settings=cfg)
    client = ClienteTesteASGI(app)

    html = client.get("/").text
    modulos_js = (
        "formatters.js",
        "api.js",
        "modulo-importacao.js",
        "modulo-explorador.js",
        "modulo-revisao.js",
        "app.js",
        "pdf-viewer.js",
    )
    for nome in modulos_js:
        caminho = DIRETORIO_STATIC / "js" / nome
        assert caminho.is_file(), f"Módulo JS ausente: {caminho}"
        assert f"/static/js/{nome}" in html

    assert "formEl.reset()" not in (DIRETORIO_STATIC / "js" / "modulo-importacao.js").read_text(
        encoding="utf-8"
    )
    app_js = (DIRETORIO_STATIC / "js" / "app.js").read_text(encoding="utf-8")
    assert "Object.getOwnPropertyDescriptors" in app_js

    imp_js = (DIRETORIO_STATIC / "js" / "modulo-importacao.js").read_text(encoding="utf-8")
    assert "limparCamposSelecao" in imp_js
    assert 'dados.status_geral === "concluido"' in imp_js
    for modo in ("padrao", "rapido", "semantico", "lexical"):
        estrategia, base, temporal = resolver_configuracao_alinhamento(
            OpcoesProcessamento(modo_alinhamento=modo)
        )
        assert f'estrategia: "{estrategia}"' in imp_js
        assert f'base: "{base}"' in imp_js
        assert f'temporal: "{temporal}"' in imp_js


def test_upload_ignorado_quando_etapa_desmarcada_e_streaming(tmp_path: Path) -> None:
    cfg = _settings_isoladas(tmp_path)

    class FakeTranscreverMinimo:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def executar(self, caminho: Path, titulo: str | None = None) -> Aula:
            return _aula_ficticia(caminho)

    gestor = GerenciadorProcessamento(
        settings=cfg,
        executar_sincrono=True,
        repo_doc_cls=lambda _: MagicMock(),
        repo_aula_cls=lambda _: MagicMock(),
        repo_alin_cls=lambda _: MagicMock(),
        transcrever_cls=FakeTranscreverMinimo,
        inspetor_audio_cls=lambda: MagicMock(),
        provedor_whisperx_cls=lambda **kwargs: MagicMock(),
    )
    app = criar_app(settings=cfg, gerenciador=gestor)
    client = ClienteTesteASGI(app)

    conteudo_audio = b"RIFF" + (b"A" * 2048)
    resp1 = client.post(
        "/api/documentos",
        files={
            "arquivo_pdf": ("ignorado.pdf", b"%PDF-1.4 nao deve salvar", "application/pdf"),
            "arquivo_audio": ("aula.wav", conteudo_audio, "audio/wav"),
        },
        data={"executar_transcricao": "on"},
    )
    assert resp1.status_code == 202

    arquivos_salvos = sorted(p.name for p in gestor.diretorio_uploads.iterdir())
    assert arquivos_salvos == ["aula.wav"]

    resp2 = client.post(
        "/api/documentos",
        files={"arquivo_audio": ("aula.wav", conteudo_audio, "audio/wav")},
        data={"executar_transcricao": "on"},
    )
    assert resp2.status_code == 202
    arquivos_apos = sorted(p.name for p in gestor.diretorio_uploads.iterdir())
    assert len(arquivos_apos) == 2
    assert any(nome.startswith("aula-") and nome.endswith(".wav") for nome in arquivos_apos)


def test_listar_documentos_sem_n_mais_um_e_404_sem_vazar_caminho(tmp_path: Path) -> None:
    cfg = _settings_isoladas(tmp_path)
    banco = Path(cfg.database_path)

    pdf1 = tmp_path / "segredo_1.pdf"
    pdf2 = tmp_path / "segredo_2.pdf"
    audio1 = tmp_path / "audio_secreto.wav"
    pdf1.write_bytes(b"%PDF-1.4")
    pdf2.write_bytes(b"%PDF-1.4")
    audio1.write_bytes(b"RIFF")

    doc1 = _documento_ficticio(pdf1)
    doc2 = Documento(
        id_documento="doc-web-2",
        uri_origem=str(pdf2),
        titulo="Material Web 2",
        paginas=[
            PaginaDocumento(
                id_pagina="doc-web-2-p1",
                numero_pagina=1,
                texto_nativo="Conteúdo doc 2",
                texto_normalizado="Conteúdo doc 2",
                metodo_extracao="native",
                unidades=[],
            )
        ],
        versao_processamento="v1",
        proveniencia=doc1.proveniencia,
    )
    aula = _aula_ficticia(audio1)

    repo_doc = RepositorioDocumentoSQLite(banco)
    repo_aula = RepositorioAulaSQLite(banco)
    repo_doc.salvar(doc1)
    repo_doc.salvar(doc2)
    repo_aula.salvar(aula)

    app = criar_app(settings=cfg)
    client = ClienteTesteASGI(app)

    with patch.object(
        RepositorioAulaSQLite, "listar", autospec=True, wraps=RepositorioAulaSQLite.listar
    ) as spy_listar_aulas:
        resp_lista = client.get("/api/documentos")
        assert resp_lista.status_code == 200
        assert len(resp_lista.json()) == 2
        assert spy_listar_aulas.call_count == 1

    pdf1.unlink()
    audio1.unlink()

    resp_pdf_404 = client.get("/api/documentos/doc-web-1/pdf")
    assert resp_pdf_404.status_code == 404
    assert str(tmp_path) not in resp_pdf_404.json()["detail"]

    resp_img_404 = client.get("/api/documentos/doc-web-1/paginas/1/imagem")
    assert resp_img_404.status_code == 404
    assert str(tmp_path) not in resp_img_404.json()["detail"]

    resp_audio_404 = client.get("/api/documentos/doc-web-1/audio")
    assert resp_audio_404.status_code == 404
    assert str(tmp_path) not in resp_audio_404.json()["detail"]


def test_fronteira_hexagonal_adaptador_web() -> None:
    import ast

    from anotai.adapters.inbound.web.app import DIRETORIO_WEB

    prefixos_proibidos = (
        "anotai.adapters.outbound",
        "anotai.adapters.inbound.cli",
        "pymupdf",
        "fitz",
        "ollama",
    )
    for arquivo_py in sorted(DIRETORIO_WEB.glob("*.py")):
        arvore = ast.parse(arquivo_py.read_text(encoding="utf-8"), filename=str(arquivo_py))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                for alias in no.names:
                    assert not alias.name.startswith(prefixos_proibidos), (
                        f"Violação hexagonal em {arquivo_py.name}: import {alias.name}"
                    )
            elif isinstance(no, ast.ImportFrom) and no.module:
                assert not no.module.startswith(prefixos_proibidos), (
                    f"Violação hexagonal em {arquivo_py.name}: from {no.module}"
                )


def test_vinculo_serializa_metricas_estruturadas_e_remocao_parcial(tmp_path: Path) -> None:
    cfg = _settings_isoladas(tmp_path)
    banco = Path(cfg.database_path)
    pdf_path = tmp_path / "aula.pdf"
    audio_path = tmp_path / "aula.wav"
    pdf_path.write_bytes(b"%PDF-1.4")
    audio_path.write_bytes(b"RIFF")

    doc = _documento_ficticio(pdf_path)
    aula = _aula_ficticia(audio_path)

    RepositorioDocumentoSQLite(banco).salvar(doc)
    RepositorioAulaSQLite(banco).salvar(aula)

    alin = Alinhamento(
        id_alinhamento=Alinhamento.gerar_id_estavel("int-1", doc.id_documento, "hierarchical_hmm"),
        id_aula=aula.id_aula,
        id_documento=doc.id_documento,
        id_intervalo="int-1",
        ids_paginas=["doc-web-1-p1", "doc-web-1-p2"],
        ids_unidades=["doc-web-1-p1-u1", "doc-web-1-p2-u1"],
        status="aligned",
        tipo_relacao="direct",
        confianca=0.81,
        estrategia="hierarchical_hmm",
        justificativa=(
            "estrategia=hierarchical_hmm | "
            "pag_topo=doc-web-1-p1(final=0.8100, sim=0.7500, temp=0.9000, vis=0.1000) | "
            "gamma_abs=0.0500"
        ),
        origem="automatic",
    )
    RepositorioAlinhamentoSQLite(banco).salvar_lote([alin])

    app = criar_app(settings=cfg)
    client = ClienteTesteASGI(app)

    grafo = client.get("/api/documentos/doc-web-1").json()
    vinculo = grafo["intervalos"][0]["vinculo"]
    assert vinculo["metricas"] == [
        {"rotulo": "Conf.", "valor": "81%"},
        {"rotulo": "Princ.", "valor": "Pág. 1"},
        {"rotulo": "Texto", "valor": "75%"},
        {"rotulo": "Temp.", "valor": "90%"},
        {"rotulo": "Visual", "valor": "10%"},
        {"rotulo": "Abst.", "valor": "5%"},
    ]

    resp_del_pag = client.delete(f"/api/vinculos/{alin.id_alinhamento}?id_pagina=doc-web-1-p1")
    assert resp_del_pag.status_code == 200
    atualizado = resp_del_pag.json()
    assert atualizado["ids_paginas"] == ["doc-web-1-p2"]
    assert atualizado["ids_unidades"] == ["doc-web-1-p2-u1"]
    assert atualizado["manual"] is True
    assert atualizado["metricas"] is None


def test_fronteira_hexagonal_dominio_e_aplicacao() -> None:
    import ast

    import anotai

    raiz_pacote = Path(anotai.__file__).resolve().parent
    proibidos_comuns = (
        "anotai.adapters",
        "anotai.bootstrap",
        "anotai.config",
        "fastapi",
        "sqlalchemy",
        "pymupdf",
        "fitz",
        "ollama",
        "whisperx",
        "torch",
        "bm25s",
        "numpy",
    )

    for camada, proibidos in (
        ("domain", (*proibidos_comuns, "anotai.application")),
        ("application", proibidos_comuns),
    ):
        for arquivo_py in sorted((raiz_pacote / camada).rglob("*.py")):
            arvore = ast.parse(arquivo_py.read_text(encoding="utf-8"), filename=str(arquivo_py))
            for no in ast.walk(arvore):
                if isinstance(no, ast.Import):
                    for alias in no.names:
                        assert not alias.name.startswith(proibidos), (
                            f"Violação hexagonal em {camada}/{arquivo_py.name}: import {alias.name}"
                        )
                elif isinstance(no, ast.ImportFrom) and no.module:
                    assert not no.module.startswith(proibidos), (
                        f"Violação hexagonal em {camada}/{arquivo_py.name}: from {no.module}"
                    )


def test_traducoes_unidades_pdf_viewer_e_selecao_vinculo_mais_recente() -> None:
    from anotai.application.use_cases import ConsultarAcervo

    pdf_viewer_js = (DIRETORIO_STATIC / "js" / "pdf-viewer.js").read_text(encoding="utf-8")
    for tipo in sorted(UnidadeDocumento.TIPOS_VALIDOS):
        assert f"{tipo}:" in pdf_viewer_js

    auto_antigo = Alinhamento(
        id_alinhamento="align-auto-1",
        id_aula="aula-1",
        id_documento="doc-1",
        id_intervalo="int-1",
        ids_paginas=["p1"],
        status="aligned",
        tipo_relacao="direct",
        confianca=0.6,
        estrategia="bm25",
        origem="automatic",
    )
    auto_recente = Alinhamento(
        id_alinhamento="align-auto-2",
        id_aula="aula-1",
        id_documento="doc-1",
        id_intervalo="int-1",
        ids_paginas=["p2"],
        status="aligned",
        tipo_relacao="direct",
        confianca=0.85,
        estrategia="hierarchical_hmm",
        origem="automatic",
    )
    ativos_auto = ConsultarAcervo.selecionar_vinculos_ativos([auto_antigo, auto_recente])
    assert ativos_auto["int-1"].id_alinhamento == "align-auto-2"

    manual = Alinhamento(
        id_alinhamento="align-manual-1",
        id_aula="aula-1",
        id_documento="doc-1",
        id_intervalo="int-1",
        ids_paginas=["p3"],
        status="aligned",
        tipo_relacao="reference",
        confianca=1.0,
        estrategia="manual",
        origem="manual",
    )
    ativos_com_manual = ConsultarAcervo.selecionar_vinculos_ativos(
        [auto_antigo, manual, auto_recente]
    )
    assert ativos_com_manual["int-1"].id_alinhamento == "align-manual-1"


