from __future__ import annotations

import logging
import re
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from anotai.application.use_cases import (
    AgrupadorIntervalos,
    AlinharAula,
    ImportarDocumento,
    RecuperarCandidatos,
    TranscreverAula,
    calcular_limiar_abstencao_efetivo,
    resolver_preset_alinhamento,
)
from anotai.bootstrap import (
    construir_indices_busca,
    criar_analisador_visual,
    criar_extrator_documento,
    criar_inspetor_audio,
    criar_provedor_transcricao,
    obter_classes_repositorios,
)
from anotai.config import Settings
from anotai.domain.entities import Alinhamento, Aula, Documento, UnidadeDocumento
from anotai.domain.value_objects import ParametrosHMM, PesosAlinhamento, StatusAlinhamento

logger = logging.getLogger(__name__)

EXTENSOES_AUDIO_SUPORTADAS = (".wav", ".mp3", ".m4a", ".mp4", ".mkv", ".webm", ".ogg", ".flac")


@dataclass(slots=True)
class OpcoesProcessamento:
    """Parâmetros completos configuráveis na tela de importação e processamento."""

    executar_pdf: bool = True
    executar_transcricao: bool = True
    executar_alinhamento: bool = True
    id_documento_existente: str | None = None
    id_aula_existente: str | None = None

    # PDF e OCR visual
    metodo_pdf: str = "native_then_ocr"
    provedor_visual: str = "ollama"
    modelo_visual: str = "qwen3-vl:8b"
    temperatura_visual: float = 0.0
    seed_visual: int = 42
    pensar_visual: bool = False

    # Áudio, ASR e segmentação
    titulo_aula: str | None = None
    provedor_transcricao: str = "whisperx"
    idioma_transcricao: str = "pt-BR"
    modelo_whisperx: str = "large-v3"
    dispositivo_whisperx: str = "cuda"
    tipo_computacao: str = "float16"
    alinhar_fonemas: bool = False
    limiar_silencio: float = 1.5
    duracao_minima_intervalo: float = 10.0
    duracao_maxima_intervalo: float = 45.0

    # Alinhamento temporal e hierárquico
    modo_alinhamento: str = "padrao"
    estrategia_alinhamento: str = "hierarchical"
    estrategia_base: str = "hybrid"
    modelo_temporal: str = "hmm"
    provedor_embedding: str = "ollama"
    modelo_embedding: str = "bge-m3:567m"
    limiar_abstencao: float = 0.0
    max_paginas: int = 3
    max_unidades: int = 5
    peso_similaridade: float = 0.75
    peso_temporal: float = 0.20
    peso_visual: float = 0.05
    janela_temporal: int = 2
    temperatura_hmm: float = 0.15

    @classmethod
    def a_partir_de_settings(cls, settings: Settings) -> OpcoesProcessamento:
        return cls(
            provedor_visual=settings.visual_provider,
            modelo_visual=settings.visual_model,
            temperatura_visual=settings.visual_temperature,
            seed_visual=settings.visual_seed,
            pensar_visual=settings.visual_think,
            provedor_transcricao=settings.transcription_provider,
            idioma_transcricao=settings.azure_speech_language,
            modelo_whisperx=settings.whisperx_model,
            dispositivo_whisperx=settings.whisperx_device,
            tipo_computacao=settings.whisperx_compute_type,
            alinhar_fonemas=settings.whisperx_align_phonemes,
            limiar_silencio=settings.interval_silence_threshold,
            duracao_minima_intervalo=settings.interval_min_duration,
            duracao_maxima_intervalo=settings.interval_max_duration,
            provedor_embedding=settings.embedding_provider,
            modelo_embedding=settings.embedding_model,
            limiar_abstencao=settings.abstention_threshold,
            peso_similaridade=settings.alignment_similarity_weight,
            peso_temporal=settings.alignment_temporal_weight,
            peso_visual=settings.alignment_visual_weight,
            janela_temporal=settings.alignment_temporal_window,
            temperatura_hmm=settings.hmm_emission_temperature,
        )


@dataclass(slots=True)
class StatusEtapa:
    """Estado de execução e métricas de uma etapa individual do pipeline."""

    chave: str
    titulo: str
    estado: str = "aguardando"
    resumo: str = "Aguardando início"
    metricas: list[tuple[str, str]] = field(default_factory=list)
    mensagem_erro: str | None = None

    @property
    def rotulo_estado(self) -> str:
        rotulos = {
            "aguardando": "Aguardando",
            "executando": "Em execução",
            "concluido": "Concluído",
            "ignorado": "Ignorado",
            "cancelado": "Cancelado",
            "erro": "Falhou",
        }
        return rotulos.get(self.estado, self.estado)


@dataclass(slots=True)
class TarefaProcessamento:
    """Registro acompanhado pela interface web para status de PDF, OCR, ASR e alinhamento."""

    id_job: str
    criado_em: str
    status_geral: str
    opcoes: OpcoesProcessamento
    nome_arquivo_pdf: str | None
    nome_arquivo_audio: str | None
    etapa_pdf: StatusEtapa
    etapa_ocr: StatusEtapa
    etapa_transcricao: StatusEtapa
    etapa_alinhamento: StatusEtapa
    id_documento: str | None = None
    id_aula: str | None = None
    mensagem_erro: str | None = None

    @property
    def em_andamento(self) -> bool:
        return self.status_geral in ("aguardando", "executando")

    @property
    def rotulo_geral(self) -> str:
        rotulos = {
            "aguardando": "Na fila",
            "executando": "Processando",
            "concluido": "Concluído",
            "cancelado": "Interrompido",
            "erro": "Interrompido com erro",
        }
        return rotulos.get(self.status_geral, self.status_geral)

    @property
    def etapas(self) -> list[StatusEtapa]:
        return [
            self.etapa_pdf,
            self.etapa_ocr,
            self.etapa_transcricao,
            self.etapa_alinhamento,
        ]

    def clonar(self) -> TarefaProcessamento:
        return replace(
            self,
            etapa_pdf=replace(self.etapa_pdf, metricas=list(self.etapa_pdf.metricas)),
            etapa_ocr=replace(self.etapa_ocr, metricas=list(self.etapa_ocr.metricas)),
            etapa_transcricao=replace(
                self.etapa_transcricao, metricas=list(self.etapa_transcricao.metricas)
            ),
            etapa_alinhamento=replace(
                self.etapa_alinhamento, metricas=list(self.etapa_alinhamento.metricas)
            ),
        )


def resolver_configuracao_alinhamento(opcoes: OpcoesProcessamento) -> tuple[str, str, str]:
    """Resolve o preset de alinhamento delegando à regra de aplicação."""
    return resolver_preset_alinhamento(
        modo_alinhamento=opcoes.modo_alinhamento,
        estrategia_alinhamento=opcoes.estrategia_alinhamento,
        estrategia_base=opcoes.estrategia_base,
        modelo_temporal=opcoes.modelo_temporal,
    )


def higienizar_nome_arquivo(nome: str) -> str:
    """Remove diretórios e caracteres inseguros preservando extensão original."""
    base = Path(nome).name
    limpo = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return limpo or "arquivo"


def remover_arquivo_upload_se_orfao(
    caminho: Path | None,
    diretorio_uploads: Path,
    caminhos_em_uso: set[Path],
) -> None:
    """Remove um arquivo da pasta de uploads caso não esteja referenciado no acervo."""
    if caminho is None or not caminho.is_file():
        return
    try:
        resolvido = caminho.resolve()
        uploads_resolvido = diretorio_uploads.resolve()
    except OSError:
        return
    if not resolvido.is_relative_to(uploads_resolvido):
        return
    if resolvido not in caminhos_em_uso:
        resolvido.unlink(missing_ok=True)


class GerenciadorProcessamento:
    """Orquestra execuções do pipeline de importação e acompanha status por etapa."""

    def __init__(
        self,
        settings: Settings,
        executar_sincrono: bool = False,
        repo_doc_cls: Any = None,
        repo_aula_cls: Any = None,
        repo_alin_cls: Any = None,
        importar_doc_cls: Any = ImportarDocumento,
        transcrever_cls: Any = TranscreverAula,
        alinhar_cls: Any = AlinharAula,
        recuperador_cls: Any = RecuperarCandidatos,
        extrator_pdf_cls: Any = None,
        analisador_visual_cls: Any = None,
        inspetor_audio_cls: Any = None,
        provedor_whisperx_cls: Any = None,
        agrupador_cls: Any = AgrupadorIntervalos,
        indices_builder: Callable[..., tuple[Any, Any]] | None = None,
    ) -> None:
        padrao_doc_cls, padrao_aula_cls, padrao_alin_cls = obter_classes_repositorios()
        self.settings = settings
        self.executar_sincrono = executar_sincrono
        self._repo_doc_cls = repo_doc_cls or padrao_doc_cls
        self._repo_aula_cls = repo_aula_cls or padrao_aula_cls
        self._repo_alin_cls = repo_alin_cls or padrao_alin_cls
        self._importar_doc_cls = importar_doc_cls
        self._transcrever_cls = transcrever_cls
        self._alinhar_cls = alinhar_cls
        self._recuperador_cls = recuperador_cls
        self._extrator_pdf_cls = extrator_pdf_cls
        self._analisador_visual_cls = analisador_visual_cls
        self._inspetor_audio_cls = inspetor_audio_cls
        self._provedor_whisperx_cls = provedor_whisperx_cls
        self._agrupador_cls = agrupador_cls
        self._indices_builder = indices_builder

        self._lock = threading.Lock()
        self._tarefas: dict[str, TarefaProcessamento] = {}
        self._eventos_cancelamento: dict[str, threading.Event] = {}
        self._vinculos_doc_aula: dict[str, str] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="anotai-web")

    @property
    def diretorio_uploads(self) -> Path:
        processados = Path(self.settings.processed_directory)
        return processados.parent / "originais" / "uploads"

    def iniciar(
        self,
        opcoes: OpcoesProcessamento,
        caminho_pdf: Path | None = None,
        caminho_audio: Path | None = None,
    ) -> TarefaProcessamento:
        id_job = f"job-{uuid.uuid4().hex[:10]}"
        tarefa = TarefaProcessamento(
            id_job=id_job,
            criado_em=datetime.now().strftime("%H:%M:%S"),
            status_geral="executando",
            opcoes=opcoes,
            nome_arquivo_pdf=caminho_pdf.name if caminho_pdf else None,
            nome_arquivo_audio=caminho_audio.name if caminho_audio else None,
            etapa_pdf=StatusEtapa(
                chave="pdf",
                titulo="1. Extração de PDF",
                estado="aguardando",
                resumo="Preparando leitura do material didático",
            ),
            etapa_ocr=StatusEtapa(
                chave="ocr",
                titulo="2. OCR visual",
                estado="aguardando",
                resumo=(
                    "Análise visual de páginas gráficas habilitada"
                    if opcoes.metodo_pdf == "native_then_ocr"
                    else "Desativado (somente texto nativo)"
                ),
            ),
            etapa_transcricao=StatusEtapa(
                chave="transcricao",
                titulo="3. Transcrição",
                estado="aguardando",
                resumo="Pronto para transcrever áudio e segmentar intervalos",
            ),
            etapa_alinhamento=StatusEtapa(
                chave="alinhamento",
                titulo="4. Alinhamento temporal",
                estado="aguardando",
                resumo="Aguardando insumos para alinhar aula e documento",
            ),
        )

        with self._lock:
            self._tarefas[id_job] = tarefa
            self._eventos_cancelamento[id_job] = threading.Event()

        if self.executar_sincrono:
            self._executar_pipeline(id_job, opcoes, caminho_pdf, caminho_audio)
        else:
            self._executor.submit(
                self._executar_pipeline, id_job, opcoes, caminho_pdf, caminho_audio
            )

        snapshot = self.obter_tarefa(id_job)
        assert snapshot is not None
        return snapshot

    def obter_tarefa(self, id_job: str) -> TarefaProcessamento | None:
        with self._lock:
            tarefa = self._tarefas.get(id_job)
            return tarefa.clonar() if tarefa is not None else None

    def obter_aula_associada(self, id_documento: str) -> str | None:
        with self._lock:
            return self._vinculos_doc_aula.get(id_documento)

    def remover_vinculo_documento(self, id_documento: str) -> None:
        with self._lock:
            self._vinculos_doc_aula.pop(id_documento, None)

    def remover_vinculo_aula(self, id_aula: str) -> None:
        with self._lock:
            chaves = [k for k, v in self._vinculos_doc_aula.items() if v == id_aula]
            for chave in chaves:
                self._vinculos_doc_aula.pop(chave, None)

    def cancelar(self, id_job: str) -> TarefaProcessamento | None:
        """Solicita interrupção cooperativa de uma tarefa em fila ou em execução."""
        with self._lock:
            tarefa = self._tarefas.get(id_job)
            if tarefa is None:
                return None
            evento = self._eventos_cancelamento.get(id_job)
            if evento is not None:
                evento.set()
            if tarefa.em_andamento:
                tarefa.status_geral = "cancelado"
                tarefa.mensagem_erro = "Processamento interrompido pelo usuário."
                for etapa in tarefa.etapas:
                    if etapa.estado == "executando":
                        etapa.estado = "cancelado"
                        etapa.resumo = "Interrompido pelo usuário"
                    elif etapa.estado == "aguardando":
                        etapa.estado = "ignorado"
                        etapa.resumo = "Não executado devido à interrupção"
            return tarefa.clonar()

    def _foi_cancelado(self, id_job: str) -> bool:
        evento = self._eventos_cancelamento.get(id_job)
        return evento is not None and evento.is_set()

    def _atualizar(self, id_job: str, mutador: Callable[[TarefaProcessamento], None]) -> None:
        with self._lock:
            if self._foi_cancelado(id_job):
                return
            tarefa = self._tarefas[id_job]
            mutador(tarefa)

    def _executar_pipeline(
        self,
        id_job: str,
        opcoes: OpcoesProcessamento,
        caminho_pdf: Path | None,
        caminho_audio: Path | None,
    ) -> None:
        banco_path = Path(self.settings.database_path)
        repo_doc = self._repo_doc_cls(banco_path)
        repo_aula = self._repo_aula_cls(banco_path)
        repo_alin = self._repo_alin_cls(banco_path)

        etapa_em_curso: str | None = None
        documento: Documento | None = None
        aula: Aula | None = None

        try:
            if self._foi_cancelado(id_job):
                return

            etapa_em_curso = "pdf"
            documento = self._processar_etapa_pdf_ocr(
                id_job=id_job,
                opcoes=opcoes,
                caminho_pdf=caminho_pdf,
                repo_doc=repo_doc,
            )
            if self._foi_cancelado(id_job):
                return

            etapa_em_curso = "transcricao"
            aula = self._processar_etapa_transcricao(
                id_job=id_job,
                opcoes=opcoes,
                caminho_audio=caminho_audio,
                repo_aula=repo_aula,
            )
            if self._foi_cancelado(id_job):
                return

            etapa_em_curso = "alinhamento"
            self._processar_etapa_alinhamento(
                id_job=id_job,
                opcoes=opcoes,
                documento=documento,
                aula=aula,
                repo_alin=repo_alin,
            )
            if self._foi_cancelado(id_job):
                return

            def _concluir(t: TarefaProcessamento) -> None:
                t.status_geral = "concluido"
                if documento is not None:
                    t.id_documento = documento.id_documento
                if aula is not None:
                    t.id_aula = aula.id_aula
                if documento is not None and aula is not None and opcoes.executar_alinhamento:
                    self._vinculos_doc_aula[documento.id_documento] = aula.id_aula

            self._atualizar(id_job, _concluir)

        except Exception as exc:
            logger.exception("Falha no pipeline da tarefa %s", id_job)
            mensagem = str(exc).strip() or exc.__class__.__name__

            def _marcar_erro(t: TarefaProcessamento) -> None:
                t.status_geral = "erro"
                t.mensagem_erro = mensagem
                mapa_etapas = {
                    "pdf": t.etapa_pdf,
                    "ocr": t.etapa_ocr,
                    "transcricao": t.etapa_transcricao,
                    "alinhamento": t.etapa_alinhamento,
                }
                if etapa_em_curso and etapa_em_curso in mapa_etapas:
                    alvo = mapa_etapas[etapa_em_curso]
                    alvo.estado = "erro"
                    alvo.resumo = "Processamento interrompido"
                    alvo.mensagem_erro = mensagem
                if etapa_em_curso == "pdf" and t.etapa_ocr.estado == "executando":
                    t.etapa_ocr.estado = "erro"
                    t.etapa_ocr.resumo = "Interrompido durante extração do PDF"
                    t.etapa_ocr.mensagem_erro = mensagem

                for etapa in t.etapas:
                    if etapa.estado == "aguardando":
                        etapa.estado = "ignorado"
                        etapa.resumo = "Não executado devido a falha anterior"

            self._atualizar(id_job, _marcar_erro)
        finally:
            if self._foi_cancelado(id_job):
                self._limpar_uploads_nao_salvos(
                    caminho_pdf=caminho_pdf if opcoes.executar_pdf else None,
                    caminho_audio=caminho_audio if opcoes.executar_transcricao else None,
                    repo_doc=repo_doc,
                    repo_aula=repo_aula,
                )

    def _limpar_uploads_nao_salvos(
        self,
        *,
        caminho_pdf: Path | None,
        caminho_audio: Path | None,
        repo_doc: Any,
        repo_aula: Any,
    ) -> None:
        if caminho_pdf is not None:
            docs = repo_doc.listar()
            docs_em_uso = (
                {Path(d.uri_origem).resolve() for d in docs} if isinstance(docs, list) else set()
            )
            remover_arquivo_upload_se_orfao(caminho_pdf, self.diretorio_uploads, docs_em_uso)

        if caminho_audio is not None:
            aulas = repo_aula.listar()
            aulas_em_uso = (
                {Path(a.caminho_arquivo).resolve() for a in aulas}
                if isinstance(aulas, list)
                else set()
            )
            remover_arquivo_upload_se_orfao(caminho_audio, self.diretorio_uploads, aulas_em_uso)

    def _processar_etapa_pdf_ocr(
        self,
        id_job: str,
        opcoes: OpcoesProcessamento,
        caminho_pdf: Path | None,
        repo_doc: Any,
    ) -> Documento | None:
        if caminho_pdf is not None and opcoes.executar_pdf:
            usa_ocr = opcoes.metodo_pdf == "native_then_ocr"

            def _iniciar_pdf(t: TarefaProcessamento) -> None:
                t.etapa_pdf.estado = "executando"
                t.etapa_pdf.resumo = f"Extraindo páginas e unidades de '{caminho_pdf.name}'"
                if usa_ocr:
                    t.etapa_ocr.estado = "executando"
                    t.etapa_ocr.resumo = "Analisando páginas gráficas e digitalizadas"
                else:
                    t.etapa_ocr.estado = "ignorado"
                    t.etapa_ocr.resumo = "Desativado (modo somente texto nativo)"

            self._atualizar(id_job, _iniciar_pdf)

            analisador = None
            if usa_ocr:
                analisador = criar_analisador_visual(
                    self.settings,
                    opcoes.modelo_visual,
                    temperatura=opcoes.temperatura_visual,
                    seed=opcoes.seed_visual,
                    pensar=opcoes.pensar_visual,
                    analisador_cls=self._analisador_visual_cls,
                    provedor=opcoes.provedor_visual,
                )

            extrator = criar_extrator_documento(
                analisador, extrator_cls=self._extrator_pdf_cls
            )
            caso_uso = self._importar_doc_cls(
                extrator,
                repositorio=None,
            )
            documento = caso_uso.executar(caminho_pdf, opcoes.metodo_pdf)
            if self._foi_cancelado(id_job):
                return None
            repo_doc.salvar(documento)

            total_paginas = len(documento.paginas)
            total_unidades = sum(len(p.unidades) for p in documento.paginas)
            paginas_ocr = sum(1 for p in documento.paginas if p.metodo_extracao == "mixed")
            unidades_ocr = sum(
                1
                for p in documento.paginas
                for u in p.unidades
                if u.fonte in UnidadeDocumento.FONTES_OCR_VISUAL
            )

            def _finalizar_pdf(t: TarefaProcessamento) -> None:
                t.id_documento = documento.id_documento
                t.etapa_pdf.estado = "concluido"
                t.etapa_pdf.resumo = f"Documento '{documento.titulo}' indexado"
                t.etapa_pdf.metricas = [
                    ("ID", documento.id_documento),
                    ("Páginas", str(total_paginas)),
                    ("Unidades", str(total_unidades)),
                ]
                if usa_ocr:
                    t.etapa_ocr.estado = "concluido"
                    t.etapa_ocr.resumo = "Análise visual aplicada em páginas gráficas"
                    t.etapa_ocr.metricas = [
                        ("Páginas com OCR", str(paginas_ocr)),
                        ("Unidades visuais", str(unidades_ocr)),
                    ]

            self._atualizar(id_job, _finalizar_pdf)
            return documento

        if opcoes.id_documento_existente:
            documento = repo_doc.buscar_por_id(opcoes.id_documento_existente)
            if documento is None:
                raise ValueError(
                    f"Documento selecionado '{opcoes.id_documento_existente}' "
                    "não encontrado no banco."
                )

            total_paginas = len(documento.paginas)
            total_unidades = sum(len(p.unidades) for p in documento.paginas)
            paginas_ocr = sum(1 for p in documento.paginas if p.metodo_extracao == "mixed")

            def _reutilizar_doc(t: TarefaProcessamento) -> None:
                t.id_documento = documento.id_documento
                t.etapa_pdf.estado = "concluido"
                t.etapa_pdf.resumo = f"Reutilizado do acervo: '{documento.titulo}'"
                t.etapa_pdf.metricas = [
                    ("ID", documento.id_documento),
                    ("Páginas", str(total_paginas)),
                    ("Unidades", str(total_unidades)),
                ]
                t.etapa_ocr.estado = "concluido"
                t.etapa_ocr.resumo = "Extraído anteriormente"
                t.etapa_ocr.metricas = [("Páginas com OCR", str(paginas_ocr))]

            self._atualizar(id_job, _reutilizar_doc)
            return documento

        def _ignorar_pdf(t: TarefaProcessamento) -> None:
            t.etapa_pdf.estado = "ignorado"
            t.etapa_pdf.resumo = "Nenhum PDF selecionado para esta execução"
            t.etapa_ocr.estado = "ignorado"
            t.etapa_ocr.resumo = "Nenhum PDF selecionado"

        self._atualizar(id_job, _ignorar_pdf)
        return None

    def _processar_etapa_transcricao(
        self,
        id_job: str,
        opcoes: OpcoesProcessamento,
        caminho_audio: Path | None,
        repo_aula: Any,
    ) -> Aula | None:
        if caminho_audio is not None and opcoes.executar_transcricao:
            def _iniciar_asr(t: TarefaProcessamento) -> None:
                t.etapa_transcricao.estado = "executando"
                t.etapa_transcricao.resumo = f"Transcrevendo '{caminho_audio.name}'"

            self._atualizar(id_job, _iniciar_asr)

            inspetor = criar_inspetor_audio(inspetor_cls=self._inspetor_audio_cls)
            provedor = criar_provedor_transcricao(
                modelo=opcoes.modelo_whisperx,
                dispositivo=opcoes.dispositivo_whisperx,
                tipo_computacao=opcoes.tipo_computacao,
                alinhar_fonemas=opcoes.alinhar_fonemas,
                provedor_cls=self._provedor_whisperx_cls,
                settings=self.settings,
                provedor=opcoes.provedor_transcricao,
                idioma=opcoes.idioma_transcricao,
            )
            agrupador = self._agrupador_cls(
                limiar_silencio=opcoes.limiar_silencio,
                duracao_minima=opcoes.duracao_minima_intervalo,
                duracao_maxima=opcoes.duracao_maxima_intervalo,
            )
            caso_uso = self._transcrever_cls(
                inspetor=inspetor,
                provedor=provedor,
                repositorio=repo_aula,
                agrupador=agrupador,
                diretorio_bruto=Path(self.settings.raw_transcripts_directory),
            )
            aulas_antes_raw = repo_aula.listar()
            ids_aulas_antes = (
                {a.id_aula for a in aulas_antes_raw} if isinstance(aulas_antes_raw, list) else None
            )
            titulo = opcoes.titulo_aula.strip() if opcoes.titulo_aula else None
            aula = caso_uso.executar(caminho_audio, titulo=titulo)
            if self._foi_cancelado(id_job):
                if ids_aulas_antes is not None and aula.id_aula not in ids_aulas_antes:
                    if hasattr(repo_aula, "excluir"):
                        repo_aula.excluir(aula.id_aula)
                    bruto = Path(self.settings.raw_transcripts_directory) / f"{aula.id_aula}.json"
                    bruto.unlink(missing_ok=True)
                return None

            def _finalizar_asr(t: TarefaProcessamento) -> None:
                t.id_aula = aula.id_aula
                t.etapa_transcricao.estado = "concluido"
                t.etapa_transcricao.resumo = f"Aula '{aula.titulo}' transcrita"
                t.etapa_transcricao.metricas = [
                    ("ID", aula.id_aula),
                    ("Duração", f"{aula.metadados.duracao:.1f}s"),
                    ("Segmentos", str(len(aula.segmentos))),
                    ("Intervalos", str(len(aula.intervalos))),
                    ("Idioma", aula.idioma or "auto"),
                ]

            self._atualizar(id_job, _finalizar_asr)
            return aula

        if opcoes.id_aula_existente:
            aula = repo_aula.buscar_por_id(opcoes.id_aula_existente)
            if aula is None:
                raise ValueError(
                    f"Aula selecionada '{opcoes.id_aula_existente}' não encontrada no banco."
                )

            def _reutilizar_aula(t: TarefaProcessamento) -> None:
                t.id_aula = aula.id_aula
                t.etapa_transcricao.estado = "concluido"
                t.etapa_transcricao.resumo = f"Reutilizada do acervo: '{aula.titulo}'"
                t.etapa_transcricao.metricas = [
                    ("ID", aula.id_aula),
                    ("Duração", f"{aula.metadados.duracao:.1f}s"),
                    ("Intervalos", str(len(aula.intervalos))),
                ]

            self._atualizar(id_job, _reutilizar_aula)
            return aula

        def _ignorar_asr(t: TarefaProcessamento) -> None:
            t.etapa_transcricao.estado = "ignorado"
            t.etapa_transcricao.resumo = "Nenhum áudio selecionado para esta execução"

        self._atualizar(id_job, _ignorar_asr)
        return None

    def _processar_etapa_alinhamento(
        self,
        id_job: str,
        opcoes: OpcoesProcessamento,
        documento: Documento | None,
        aula: Aula | None,
        repo_alin: Any,
    ) -> None:
        if not opcoes.executar_alinhamento:
            def _ignorar_desativado(t: TarefaProcessamento) -> None:
                t.etapa_alinhamento.estado = "ignorado"
                t.etapa_alinhamento.resumo = "Alinhamento desativado nas opções"

            self._atualizar(id_job, _ignorar_desativado)
            return

        if documento is None or aula is None:
            def _ignorar_sem_insumos(t: TarefaProcessamento) -> None:
                t.etapa_alinhamento.estado = "ignorado"
                t.etapa_alinhamento.resumo = "Requer um documento PDF e uma aula transcrita"

            self._atualizar(id_job, _ignorar_sem_insumos)
            return

        estrategia, estrategia_base, modelo_temporal = resolver_configuracao_alinhamento(opcoes)
        estrategia_busca = (
            estrategia if estrategia in ("bm25", "embedding", "hybrid") else estrategia_base
        )

        def _iniciar_alin(t: TarefaProcessamento) -> None:
            t.etapa_alinhamento.estado = "executando"
            t.etapa_alinhamento.resumo = (
                f"Alinhando {len(aula.intervalos)} intervalos explicativos"
            )

        self._atualizar(id_job, _iniciar_alin)

        indices_builder = self._indices_builder or construir_indices_busca
        modelo_override = (
            opcoes.modelo_embedding if opcoes.provedor_embedding == "ollama" else None
        )

        idx_paginas, idx_unidades = indices_builder(
            estrategia_busca,
            self.settings,
            modelo_override=modelo_override,
            provedor_override=opcoes.provedor_embedding,
        )
        recuperador = self._recuperador_cls(
            indice_paginas=idx_paginas,
            indice_unidades=idx_unidades,
            estrategia=estrategia_busca,
            top_k_paginas=max(len(documento.paginas), 5),
            top_k_unidades=max(opcoes.max_unidades * 3, 10),
            limiar_abstencao=0.0,
        )
        sem_temporal = (
            opcoes.modo_alinhamento.strip().lower() == "personalizado"
            and opcoes.modelo_temporal.strip().lower() == "none"
        )
        usa_hmm_efetivo = modelo_temporal == "hmm" and not sem_temporal
        limiar_efetivo = calcular_limiar_abstencao_efetivo(
            opcoes.limiar_abstencao, usa_hmm_efetivo
        )
        pesos = PesosAlinhamento(
            peso_similaridade=opcoes.peso_similaridade,
            peso_temporal=0.0 if sem_temporal else opcoes.peso_temporal,
            peso_visual=opcoes.peso_visual,
            janela_temporal=opcoes.janela_temporal,
        )
        params_hmm = ParametrosHMM(
            temperatura_emissao=opcoes.temperatura_hmm,
            piso_emissao=self.settings.hmm_emission_floor,
            prior_abstencao_emissao=self.settings.hmm_abstention_emission_prior,
            peso_permanencia=self.settings.hmm_stay_weight,
            peso_adjacente=self.settings.hmm_adjacent_weight,
            peso_salto_base=self.settings.hmm_jump_base_weight,
            decaimento_salto=self.settings.hmm_jump_decay,
            piso_salto=self.settings.hmm_jump_floor,
        )
        modelo_efetivo = "none" if sem_temporal else modelo_temporal
        estrategia_composta = f"{estrategia}_{modelo_efetivo}+{estrategia_busca}"
        if self._alinhar_cls is AlinharAula:
            alinhador = self._alinhar_cls(
                recuperador=recuperador,
                repositorio_alinhamento=repo_alin,
                estrategia=estrategia,
                modelo_temporal=modelo_temporal,
                pesos=pesos,
                parametros_hmm=params_hmm,
                limiar_abstencao=limiar_efetivo,
                max_paginas=opcoes.max_paginas,
                max_unidades=opcoes.max_unidades,
                nome_estrategia_persistida=estrategia_composta,
            )
            resultados = alinhador.executar(aula, documento)
        else:
            alinhador = self._alinhar_cls(
                recuperador=recuperador,
                repositorio_alinhamento=None,
                estrategia=estrategia,
                modelo_temporal=modelo_temporal,
                pesos=pesos,
                parametros_hmm=params_hmm,
                limiar_abstencao=limiar_efetivo,
                max_paginas=opcoes.max_paginas,
                max_unidades=opcoes.max_unidades,
            )
            resultados = alinhador.executar(aula, documento)

            alinhamentos_para_salvar: list[Alinhamento] = []
            for r in resultados:
                a = r.alinhamento
                alinhamentos_para_salvar.append(
                    Alinhamento(
                        id_alinhamento=Alinhamento.gerar_id_estavel(
                            a.id_intervalo,
                            a.id_documento,
                            estrategia_composta,
                            a.origem,
                        ),
                        id_aula=a.id_aula,
                        id_documento=a.id_documento,
                        id_intervalo=a.id_intervalo,
                        ids_paginas=list(a.ids_paginas),
                        ids_unidades=list(a.ids_unidades),
                        status=a.status,
                        tipo_relacao=a.tipo_relacao,
                        confianca=a.confianca,
                        estrategia=estrategia_composta,
                        ids_evidencias=list(a.ids_evidencias),
                        versao_processamento=a.versao_processamento,
                        justificativa=a.justificativa,
                        origem=a.origem,
                    )
                )
            if alinhamentos_para_salvar:
                repo_alin.salvar_lote(alinhamentos_para_salvar)

        total = len(resultados)
        alinhados = sum(
            1 for r in resultados if r.alinhamento.status == StatusAlinhamento.ALINHADO.value
        )
        abstidos = total - alinhados
        confianca_media = (
            sum(r.alinhamento.confianca for r in resultados) / total if total else 0.0
        )

        def _finalizar_alin(t: TarefaProcessamento) -> None:
            t.etapa_alinhamento.estado = "concluido"
            t.etapa_alinhamento.resumo = "Alinhamento salvo e indexado"
            t.etapa_alinhamento.metricas = [
                ("Alinhados", f"{alinhados}/{total}"),
                ("Abstenções", str(abstidos)),
                ("Confiança média", f"{confianca_media:.2f}"),
            ]

        self._atualizar(id_job, _finalizar_alin)
