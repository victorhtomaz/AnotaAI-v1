(() => {
    "use strict";

    const fmtNumero1 = new Intl.NumberFormat("pt-BR", {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
    });
    const fmtNumero2 = new Intl.NumberFormat("pt-BR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
    const fmtInteiro = new Intl.NumberFormat("pt-BR", {
        maximumFractionDigits: 0,
    });

    function criarOpcoesIniciais() {
        return {
            executar_pdf: true,
            executar_transcricao: true,
            executar_alinhamento: true,
            metodo_pdf: "native_then_ocr",
            modelo_visual: "qwen3-vl:8b",
            temperatura_visual: 0.0,
            seed_visual: 42,
            pensar_visual: false,
            titulo_aula: "",
            modelo_whisperx: "large-v3",
            dispositivo_whisperx: "cuda",
            tipo_computacao: "float16",
            alinhar_fonemas: false,
            limiar_silencio: 1.5,
            duracao_minima_intervalo: 10.0,
            duracao_maxima_intervalo: 45.0,
            modo_alinhamento: "padrao",
            estrategia_alinhamento: "hierarchical",
            estrategia_base: "hybrid",
            modelo_temporal: "hmm",
            modelo_embedding: "bge-m3:567m",
            limiar_abstencao: 0.0,
            max_paginas: 3,
            max_unidades: 5,
            peso_similaridade: 0.75,
            peso_temporal: 0.2,
            peso_visual: 0.05,
            janela_temporal: 2,
            temperatura_hmm: 0.15,
        };
    }

    function criarStoreAnotai() {
        const ehMac =
            typeof navigator !== "undefined" &&
            /Mac|iPhone|iPad|iPod/i.test(navigator.platform || navigator.userAgent || "");

        // Instâncias externas mantidas fora da reatividade do Alpine (Proxy quebra #private fields do PDF.js)
        let pdfViewerInstancia = null;
        let audioElInstancia = null;
        let pdfContainerElInstancia = null;

        return {
            abaAtiva: "importacao",
            carregandoAcervo: false,
            carregandoDocumento: false,
            submetendoProcessamento: false,
            cancelandoJob: false,
            confirmandoCancelamento: false,
            erroGeral: null,
            erroImportacao: null,
            avisoPdf: null,

            atalhoBusca: ehMac ? "⌘K" : "Ctrl+K",
            unidadesAbertas: true,
            filtroAcervo: "vinculados",
            filtrosMobileAbertos: false,
            toast: null,
            _toastTimer: null,
            _atalhosRegistrados: false,

            opcoes: criarOpcoesIniciais(),
            opcoesPadrao: criarOpcoesIniciais(),
            idDocumentoExistente: "",
            idAulaExistente: "",
            nomeArquivoPdf: "",
            nomeArquivoAudio: "",

            jobAtual: null,
            _pollingTimer: null,

            documentos: [],
            aulas: [],
            documentoAtivo: null,

            get documentosVinculados() {
                return this.documentos.filter((doc) => Boolean(doc.id_aula));
            },

            get documentosAcervoVisiveis() {
                return this.filtroAcervo === "todos"
                    ? this.documentos
                    : this.documentosVinculados;
            },

            formatarDecimal(valor, casas = 1) {
                const n = Number(valor);
                if (!Number.isFinite(n)) {
                    return "0";
                }
                if (casas === 0) {
                    return fmtInteiro.format(n);
                }
                return casas === 2 ? fmtNumero2.format(n) : fmtNumero1.format(n);
            },

            formatarDuracaoCurta(segundos) {
                const n = Number(segundos);
                if (!Number.isFinite(n) || n <= 0) {
                    return "0 s";
                }
                if (n >= 60) {
                    return this.formatarTempo(n);
                }
                return `${fmtNumero1.format(n)} s`;
            },

            rotuloStatusVinculo(vinculo) {
                if (!vinculo || vinculo.abstido) {
                    return { classe: "estado-abstencao", texto: "∅ Sem vínculo" };
                }
                if (vinculo.manual) {
                    return { classe: "estado-manual", texto: "Manual" };
                }
                return { classe: "estado-automatico", texto: "Auto" };
            },

            exibirToast(mensagem, desfazer = null) {
                if (this._toastTimer !== null) {
                    window.clearTimeout(this._toastTimer);
                    this._toastTimer = null;
                }
                this.toast = { mensagem, desfazer };
                this._toastTimer = window.setTimeout(() => {
                    this.toast = null;
                    this._toastTimer = null;
                }, desfazer ? 7000 : 4000);
            },

            fecharToast() {
                if (this._toastTimer !== null) {
                    window.clearTimeout(this._toastTimer);
                    this._toastTimer = null;
                }
                this.toast = null;
            },

            async executarDesfazer() {
                const fn = this.toast?.desfazer;
                this.fecharToast();
                if (typeof fn === "function") {
                    await fn();
                }
            },

            selecionarAba(aba) {
                if (aba !== "importacao" && aba !== "explorador") {
                    return;
                }
                this.abaAtiva = aba;
                this._atualizarUrl();
            },

            _atualizarUrl() {
                try {
                    const params = new URLSearchParams();
                    if (this.abaAtiva === "explorador") {
                        params.set("aba", "explorador");
                    }
                    if (this.documentoAtivo?.id_documento) {
                        params.set("doc", this.documentoAtivo.id_documento);
                        if (this.documentoAtivo.id_aula) {
                            params.set("aula", this.documentoAtivo.id_aula);
                        }
                        if (Number(this.paginaAtual) > 1) {
                            params.set("pag", String(this.paginaAtual));
                        }
                    }
                    if (this.filtroOrigem && this.filtroOrigem !== "todos") {
                        params.set("origem", this.filtroOrigem);
                    }
                    if (this.termoBusca && this.termoBusca.trim()) {
                        params.set("q", this.termoBusca.trim());
                    }
                    const qs = params.toString();
                    const novaUrl = qs
                        ? `${window.location.pathname}?${qs}`
                        : window.location.pathname;
                    window.history.replaceState(null, "", novaUrl);
                } catch {
                    // ignora ambientes sem history API mutável
                }
            },

            _registrarAtalhosTeclado() {
                if (this._atalhosRegistrados || typeof window === "undefined") {
                    return;
                }
                this._atalhosRegistrados = true;
                window.addEventListener("keydown", (ev) => {
                    const alvo = ev.target;
                    const emCampo =
                        alvo &&
                        (alvo.tagName === "INPUT" ||
                            alvo.tagName === "TEXTAREA" ||
                            alvo.tagName === "SELECT" ||
                            alvo.isContentEditable);
                    const emControle =
                        emCampo ||
                        (alvo &&
                            (alvo.tagName === "BUTTON" ||
                                alvo.tagName === "SUMMARY" ||
                                alvo.tagName === "A" ||
                                alvo.tagName === "AUDIO"));

                    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") {
                        if (this.abaAtiva === "explorador" || this.documentoAtivo) {
                            ev.preventDefault();
                            if (this.abaAtiva !== "explorador") {
                                this.selecionarAba("explorador");
                            }
                            window.requestAnimationFrame(() => {
                                const campo = document.getElementById("busca-texto");
                                campo?.focus();
                                campo?.select?.();
                            });
                        }
                        return;
                    }

                    if (!emCampo && ev.key === "/" && this.abaAtiva === "explorador") {
                        ev.preventDefault();
                        document.getElementById("busca-texto")?.focus();
                        return;
                    }

                    if (
                        !emControle &&
                        !ev.ctrlKey &&
                        !ev.metaKey &&
                        !ev.altKey &&
                        this.abaAtiva === "explorador" &&
                        this.documentoAtivo
                    ) {
                        if (ev.key === "ArrowLeft") {
                            ev.preventDefault();
                            this.irParaPagina(this.paginaAtual - 1);
                            return;
                        }
                        if (ev.key === "ArrowRight") {
                            ev.preventDefault();
                            this.irParaPagina(this.paginaAtual + 1);
                            return;
                        }
                        if (ev.key === " ") {
                            if (audioElInstancia && this.documentoAtivo.url_audio) {
                                ev.preventDefault();
                                if (audioElInstancia.paused) {
                                    audioElInstancia.play().catch(() => {});
                                } else {
                                    audioElInstancia.pause();
                                }
                                return;
                            }
                        }
                    }

                    if (ev.key === "Escape") {
                        if (this.confirmandoCancelamento) {
                            this.confirmandoCancelamento = false;
                        } else if (this.revisaoAbertaId !== null) {
                            this.revisaoAbertaId = null;
                        } else if (
                            alvo &&
                            alvo.id === "busca-texto" &&
                            this.termoBusca
                        ) {
                            this.termoBusca = "";
                            this._atualizarUrl();
                        }
                    }
                });
            },

            rotuloEstrategiaAlinhamento(estrategia) {
                if (!estrategia) {
                    return "";
                }
                const mapaLegado = {
                    hierarchical_hmm: "Hierárquico · HMM",
                    hierarchical: "Hierárquico",
                    temporal_hmm: "Por página · HMM",
                    temporal: "Por página",
                    hybrid: "Híbrido (BM25 + Embeddings)",
                    bm25: "BM25 (lexical)",
                    embedding: "Embeddings (semântico)",
                    manual: "Somente revisões manuais",
                };
                if (mapaLegado[estrategia]) {
                    return mapaLegado[estrategia];
                }
                const [parteEstrutural, base] = estrategia.split("+");
                if (!base) {
                    return estrategia;
                }
                const [estrutural, temporal] = parteEstrutural.split("_");
                const rotEstrutural =
                    estrutural === "hierarchical"
                        ? "Hierárquico"
                        : estrutural === "temporal"
                          ? "Por página"
                          : estrutural;
                const rotTemporal =
                    temporal === "hmm"
                        ? "HMM"
                        : temporal === "kernel"
                          ? "Kernel"
                          : temporal === "none"
                            ? "Sem temporal"
                            : temporal;
                const rotBase =
                    base === "hybrid"
                        ? "Híbrido"
                        : base === "bm25"
                          ? "BM25"
                          : base === "embedding"
                            ? "Embeddings"
                            : base;
                return [rotEstrutural, rotTemporal, rotBase].filter(Boolean).join(" · ");
            },

            get opcoesAlinhamentoDisponiveis() {
                const vinculos = this.documentoAtivo?.vinculos || [];
                if (!vinculos.length) {
                    return [];
                }

                const contagemAuto = new Map();
                const intervalosManuais = new Set();
                for (const v of vinculos) {
                    if (v.manual) {
                        intervalosManuais.add(v.id_intervalo);
                    } else {
                        if (!contagemAuto.has(v.estrategia)) {
                            contagemAuto.set(v.estrategia, new Set());
                        }
                        contagemAuto.get(v.estrategia).add(v.id_intervalo);
                    }
                }

                const opcoes = [];
                if (intervalosManuais.size > 0 && contagemAuto.size > 0) {
                    opcoes.push({
                        valor: "combinado",
                        rotulo: "Automático + revisões manuais",
                    });
                }
                for (const [estrategia, ids] of contagemAuto.entries()) {
                    const nome = this.rotuloEstrategiaAlinhamento(estrategia);
                    opcoes.push({
                        valor: estrategia,
                        rotulo: `${nome} (${ids.size} intervalos)`,
                    });
                }
                if (intervalosManuais.size > 0) {
                    opcoes.push({
                        valor: "manual",
                        rotulo: `Somente revisões manuais (${intervalosManuais.size} intervalos)`,
                    });
                }
                return opcoes;
            },

            selecionarEstrategiaAlinhamento(valor, sincronizarPdf = true) {
                this.estrategiaAlinhamentoAtiva = valor;
                this.revisaoAbertaId = null;
                if (!this.documentoAtivo) {
                    return;
                }
                const vinculos = this.documentoAtivo.vinculos || [];
                for (const inter of this.documentoAtivo.intervalos || []) {
                    const candidatos = vinculos.filter(
                        (v) => v.id_intervalo === inter.id_intervalo
                    );
                    if (valor === "combinado") {
                        inter.vinculo =
                            candidatos.find((v) => v.manual) || candidatos[0] || null;
                    } else if (valor === "manual") {
                        inter.vinculo = candidatos.find((v) => v.manual) || null;
                    } else {
                        inter.vinculo =
                            candidatos.find(
                                (v) => !v.manual && v.estrategia === valor
                            ) || null;
                    }
                }
                if (sincronizarPdf) {
                    this._sincronizarDestaquesPdf();
                }
            },

            _registrarVinculoNaLista(vinculo) {
                if (!this.documentoAtivo || !vinculo) {
                    return;
                }
                const lista = this.documentoAtivo.vinculos || [];
                const idx = lista.findIndex(
                    (v) => v.id_alinhamento === vinculo.id_alinhamento
                );
                if (idx >= 0) {
                    lista.splice(idx, 1, vinculo);
                } else {
                    lista.push(vinculo);
                }
            },

            paginaAtual: 1,
            zoomPdf: 1.15,
            velocidadeAudio: 1,
            sincronizarAudioPdf: true,
            intervaloAtivoId: null,
            segmentoAtivoId: null,
            unidadeSelecionadaId: null,
            paginaFiltroId: null,

            termoBusca: "",
            filtroOrigem: "todos",
            estrategiaAlinhamentoAtiva: "",

            revisaoAbertaId: null,
            salvandoRevisao: false,
            rascunhoRevisao: {
                ids_paginas: [],
                ids_unidades: [],
                tipo_relacao: "direct",
                justificativa: "",
            },

            async init() {
                this._registrarAtalhosTeclado();
                const params = new URLSearchParams(window.location.search);
                const abaParam = params.get("aba");
                const docParam = params.get("doc");
                const aulaParam = params.get("aula");
                const pagParam = Number(params.get("pag"));
                const origemParam = params.get("origem");
                const buscaParam = params.get("q");

                if (abaParam === "explorador" || docParam) {
                    this.abaAtiva = "explorador";
                }
                if (
                    origemParam &&
                    ["todos", "automatic", "manual", "abstained"].includes(origemParam)
                ) {
                    this.filtroOrigem = origemParam;
                }
                if (buscaParam) {
                    this.termoBusca = buscaParam;
                }

                await Promise.all([this.carregarOpcoesPadrao(), this.carregarAcervo()]);

                if (docParam) {
                    await this.abrirDocumento(docParam, aulaParam || null, true);
                    if (Number.isInteger(pagParam) && pagParam > 1) {
                        await this.irParaPagina(pagParam);
                    }
                }
            },

            conectarElementos(audioEl, pdfContainerEl) {
                if (audioEl) {
                    audioElInstancia = audioEl;
                }
                if (pdfContainerEl && pdfContainerEl !== pdfContainerElInstancia) {
                    pdfContainerElInstancia = pdfContainerEl;
                    const ViewerCls = window.PdfViewer;
                    if (typeof ViewerCls !== "function") {
                        return;
                    }
                    pdfViewerInstancia = new ViewerCls(pdfContainerEl, {
                        onClickUnidade: (unidade) =>
                            this.selecionarUnidadeNoPdf(unidade),
                        onChangePagina: (numPagina) => {
                            this.paginaAtual = numPagina;
                            this.unidadeSelecionadaId = null;
                            if (this.paginaFiltroId !== null) {
                                this.paginaFiltroId =
                                    this.paginaAtualObj?.id_pagina || null;
                            }
                            this._sincronizarDestaquesPdf();
                            this._atualizarUrl();
                        },
                        onErro: (msg) => {
                            this.avisoPdf = msg;
                        },
                    });
                    if (this.documentoAtivo) {
                        pdfViewerInstancia.carregarDocumento(
                            this.documentoAtivo.url_pdf,
                            this.documentoAtivo.paginas
                        );
                    }
                }
            },

            async carregarOpcoesPadrao() {
                try {
                    const resp = await fetch("/api/opcoes-padrao");
                    if (!resp.ok) {
                        return;
                    }
                    const dados = await resp.json();
                    this.opcoesPadrao = { ...criarOpcoesIniciais(), ...dados };
                    this.opcoes = { ...this.opcoesPadrao };
                } catch {
                    // mantém defaults locais se endpoint falhar
                }
            },

            restaurarOpcoesPadrao(formEl) {
                this.opcoes = { ...this.opcoesPadrao };
                this.idDocumentoExistente = "";
                this.idAulaExistente = "";
                this.nomeArquivoPdf = "";
                this.nomeArquivoAudio = "";
                this.erroImportacao = null;
                if (formEl) {
                    formEl.reset();
                }
                this.exibirToast("Configurações padrão restauradas.");
            },

            aplicarPresetAlinhamento() {
                const presets = {
                    padrao: {
                        estrategia: "hierarchical",
                        base: "hybrid",
                        temporal: "hmm",
                    },
                    rapido: {
                        estrategia: "hierarchical",
                        base: "bm25",
                        temporal: "kernel",
                    },
                    semantico: {
                        estrategia: "temporal",
                        base: "embedding",
                        temporal: "none",
                    },
                    lexical: {
                        estrategia: "temporal",
                        base: "bm25",
                        temporal: "none",
                    },
                };
                const p = presets[this.opcoes.modo_alinhamento];
                if (p) {
                    this.opcoes.estrategia_alinhamento = p.estrategia;
                    this.opcoes.estrategia_base = p.base;
                    this.opcoes.modelo_temporal = p.temporal;
                }
            },

            marcarPerfilPersonalizado() {
                this.opcoes.modo_alinhamento = "personalizado";
            },

            atualizarResumoArquivo(evento, tipo) {
                const arquivo = evento.target?.files?.[0];
                const rotulo = arquivo
                    ? `${arquivo.name} (${fmtNumero2.format(arquivo.size / (1024 * 1024))} MB)`
                    : "";
                if (tipo === "pdf") {
                    this.nomeArquivoPdf = rotulo;
                } else {
                    this.nomeArquivoAudio = rotulo;
                }
            },

            async carregarAcervo() {
                this.carregandoAcervo = true;
                try {
                    const [respDocs, respAulas] = await Promise.all([
                        fetch("/api/documentos"),
                        fetch("/api/aulas"),
                    ]);
                    if (respDocs.ok) {
                        this.documentos = await respDocs.json();
                    }
                    if (respAulas.ok) {
                        this.aulas = await respAulas.json();
                    }
                } catch (erro) {
                    this.erroGeral = `Falha ao listar acervo: ${erro.message}`;
                } finally {
                    this.carregandoAcervo = false;
                }
            },

            async enviarProcessamento(formEl) {
                this.erroImportacao = null;
                this.confirmandoCancelamento = false;
                this.submetendoProcessamento = true;
                this._pararPolling();

                try {
                    const formData = new FormData(formEl);
                    const resp = await fetch("/api/documentos", {
                        method: "POST",
                        body: formData,
                    });
                    const dados = await resp.json();
                    if (!resp.ok) {
                        this.erroImportacao =
                            dados.detail || "Não foi possível iniciar o processamento.";
                        window.requestAnimationFrame(() => {
                            document.getElementById("alerta-erro-importacao")?.focus();
                        });
                        return;
                    }
                    await this._consultarStatusJob(dados.job_id);
                    this._iniciarPolling(dados.job_id);
                } catch (erro) {
                    this.erroImportacao = `Erro de comunicação com o servidor: ${erro.message}`;
                } finally {
                    this.submetendoProcessamento = false;
                }
            },

            _iniciarPolling(jobId) {
                this._pararPolling();
                if (!this.jobAtual?.em_andamento) {
                    return;
                }
                this._pollingTimer = window.setInterval(() => {
                    this._consultarStatusJob(jobId);
                }, 1500);
            },

            _pararPolling() {
                if (this._pollingTimer !== null) {
                    window.clearInterval(this._pollingTimer);
                    this._pollingTimer = null;
                }
            },

            async _consultarStatusJob(jobId) {
                try {
                    const resp = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
                    if (!resp.ok) {
                        this._pararPolling();
                        return;
                    }
                    const job = await resp.json();
                    this.jobAtual = job;
                    if (!job.em_andamento) {
                        this.confirmandoCancelamento = false;
                        this._pararPolling();
                        await this.carregarAcervo();
                    }
                } catch {
                    // mantém tentativa seguinte em caso de falha transitória
                }
            },

            async cancelarProcessamento() {
                if (!this.jobAtual?.job_id || !this.jobAtual.em_andamento) {
                    return;
                }
                this.confirmandoCancelamento = false;
                this.cancelandoJob = true;
                try {
                    const resp = await fetch(
                        `/api/jobs/${encodeURIComponent(this.jobAtual.job_id)}/cancelar`,
                        { method: "POST" }
                    );
                    if (resp.ok) {
                        this.jobAtual = await resp.json();
                        this._pararPolling();
                        await this.carregarAcervo();
                        this.exibirToast("Processamento interrompido.");
                    }
                } catch (erro) {
                    this.erroImportacao = `Falha ao interromper processamento: ${erro.message}`;
                } finally {
                    this.cancelandoJob = false;
                }
            },

            async abrirDocumento(idDocumento, idAula = null, trocarAba = true) {
                if (!idDocumento) {
                    this.documentoAtivo = null;
                    this._atualizarUrl();
                    return;
                }
                this.carregandoDocumento = true;
                this.erroGeral = null;
                this.avisoPdf = null;
                this.revisaoAbertaId = null;
                this.intervaloAtivoId = null;
                this.segmentoAtivoId = null;
                this.unidadeSelecionadaId = null;
                this.paginaFiltroId = null;

                try {
                    const query = idAula
                        ? `?id_aula=${encodeURIComponent(idAula)}`
                        : "";
                    const resp = await fetch(
                        `/api/documentos/${encodeURIComponent(idDocumento)}${query}`
                    );
                    const dados = await resp.json();
                    if (!resp.ok) {
                        this.erroGeral =
                            dados.detail || "Não foi possível carregar o documento.";
                        return;
                    }

                    this.documentoAtivo = dados;
                    const opcoesAlin = this.opcoesAlinhamentoDisponiveis;
                    this.estrategiaAlinhamentoAtiva =
                        opcoesAlin.length > 0 ? opcoesAlin[0].valor : "";
                    if (this.estrategiaAlinhamentoAtiva) {
                        this.selecionarEstrategiaAlinhamento(
                            this.estrategiaAlinhamentoAtiva,
                            false
                        );
                    }
                    this.paginaAtual = 1;
                    if (trocarAba) {
                        this.abaAtiva = "explorador";
                    }
                    this._atualizarUrl();

                    await new Promise((resolve) =>
                        window.requestAnimationFrame(() =>
                            window.requestAnimationFrame(resolve)
                        )
                    );

                    if (pdfViewerInstancia) {
                        await pdfViewerInstancia.carregarDocumento(
                            dados.url_pdf,
                            dados.paginas
                        );
                        this.zoomPdf = pdfViewerInstancia.zoom;
                        this._sincronizarDestaquesPdf();
                    }
                } catch (erro) {
                    this.erroGeral = `Erro ao carregar documento: ${erro.message}`;
                } finally {
                    this.carregandoDocumento = false;
                }
            },

            get mapaPaginasPorId() {
                const mapa = new Map();
                if (!this.documentoAtivo) {
                    return mapa;
                }
                for (const p of this.documentoAtivo.paginas) {
                    mapa.set(p.id_pagina, p);
                }
                return mapa;
            },

            get mapaUnidadesPorId() {
                const mapa = new Map();
                if (!this.documentoAtivo) {
                    return mapa;
                }
                for (const p of this.documentoAtivo.paginas) {
                    for (const u of p.unidades) {
                        mapa.set(u.id_unidade, u);
                    }
                }
                return mapa;
            },

            get paginaAtualObj() {
                if (!this.documentoAtivo) {
                    return null;
                }
                return (
                    this.documentoAtivo.paginas.find(
                        (p) => Number(p.numero_pagina) === Number(this.paginaAtual)
                    ) || null
                );
            },

            get totalPaginasDocumento() {
                return this.documentoAtivo ? this.documentoAtivo.paginas.length : 0;
            },

            get intervalosFiltrados() {
                if (!this.documentoAtivo) {
                    return [];
                }
                const termo = this.termoBusca.trim().toLowerCase();
                const origem = this.filtroOrigem;
                const pagFiltro = this.paginaFiltroId;
                const unidFiltro = this.unidadeSelecionadaId;

                return this.documentoAtivo.intervalos.filter((inter) => {
                    const vinc = inter.vinculo;
                    if (
                        origem === "automatic" &&
                        (!vinc || !vinc.automatico || vinc.abstido)
                    ) {
                        return false;
                    }
                    if (
                        origem === "manual" &&
                        (!vinc || !vinc.manual || vinc.abstido)
                    ) {
                        return false;
                    }
                    if (origem === "abstained" && vinc && !vinc.abstido) {
                        return false;
                    }

                    if (pagFiltro && (!vinc || !vinc.ids_paginas.includes(pagFiltro))) {
                        return false;
                    }

                    if (
                        unidFiltro &&
                        (!vinc || !vinc.ids_unidades.includes(unidFiltro))
                    ) {
                        const mesmoPag =
                            vinc &&
                            this.mapaUnidadesPorId.get(unidFiltro)?.id_pagina &&
                            vinc.ids_paginas.includes(
                                this.mapaUnidadesPorId.get(unidFiltro).id_pagina
                            );
                        if (!mesmoPag) {
                            return false;
                        }
                    }

                    if (!termo) {
                        return true;
                    }
                    if (inter.texto.toLowerCase().includes(termo)) {
                        return true;
                    }
                    if (vinc) {
                        for (const pid of vinc.ids_paginas) {
                            const pag = this.mapaPaginasPorId.get(pid);
                            if (pag && `página ${pag.numero_pagina}`.includes(termo)) {
                                return true;
                            }
                        }
                        for (const uid of vinc.ids_unidades) {
                            const unid = this.mapaUnidadesPorId.get(uid);
                            if (
                                unid?.texto &&
                                unid.texto.toLowerCase().includes(termo)
                            ) {
                                return true;
                            }
                        }
                    }
                    return false;
                });
            },

            get unidadesPaginaAtualFiltradas() {
                const pag = this.paginaAtualObj;
                if (!pag) {
                    return [];
                }
                const termo = this.termoBusca.trim().toLowerCase();
                if (!termo) {
                    return pag.unidades;
                }
                return pag.unidades.filter(
                    (u) =>
                        (u.texto && u.texto.toLowerCase().includes(termo)) ||
                        u.tipo.toLowerCase().includes(termo)
                );
            },

            get intervalosDaPaginaAtual() {
                const pag = this.paginaAtualObj;
                if (!pag || !this.documentoAtivo) {
                    return [];
                }
                return this.documentoAtivo.intervalos.filter(
                    (inter) =>
                        inter.vinculo &&
                        !inter.vinculo.abstido &&
                        inter.vinculo.ids_paginas.includes(pag.id_pagina)
                );
            },

            segmentosDoIntervalo(intervalo) {
                if (!this.documentoAtivo || !intervalo?.ids_segmentos?.length) {
                    return [];
                }
                const conj = new Set(intervalo.ids_segmentos);
                return this.documentoAtivo.segmentos.filter((s) =>
                    conj.has(s.id_segmento)
                );
            },

            numeroPaginaPorId(idPagina) {
                return this.mapaPaginasPorId.get(idPagina)?.numero_pagina || "?";
            },

            rotuloTipoUnidade(tipo) {
                if (typeof window.traduzirTipoUnidade === "function") {
                    return window.traduzirTipoUnidade(tipo);
                }
                return tipo || "Unidade";
            },

            descricaoUnidadePorId(idUnidade) {
                const u = this.mapaUnidadesPorId.get(idUnidade);
                if (!u) {
                    return idUnidade;
                }
                const tipoLabel = this.rotuloTipoUnidade(u.tipo);
                const textoLimpo = (u.texto || "").replace(/\s+/g, " ").trim();
                const resumo = textoLimpo
                    ? textoLimpo.length > 36
                        ? `${textoLimpo.slice(0, 36)}…`
                        : textoLimpo
                    : "conteúdo visual";
                return `Pág. ${u.numero_pagina} · ${tipoLabel}: ${resumo}`;
            },

            async focarUnidadeDoChip(intervalo, idUnidade) {
                const unid = this.mapaUnidadesPorId.get(idUnidade);
                this.intervaloAtivoId = intervalo.id_intervalo;
                this.unidadeSelecionadaId = idUnidade;
                if (unid && Number(unid.numero_pagina) !== Number(this.paginaAtual)) {
                    await this.irParaPagina(unid.numero_pagina);
                }
                this._sincronizarDestaquesPdf(intervalo.vinculo);
            },

            resumoJustificativa(vinculo) {
                const texto = (vinculo?.justificativa || "").trim();
                if (!texto) {
                    return null;
                }
                const matchPag = texto.match(
                    /pag_topo=([^\s(]+)\(final=([0-9.]+),\s*sim=([0-9.]+),\s*temp=([0-9.]+),\s*vis=([0-9.]+)\)/
                );
                if (!matchPag) {
                    return { ehEstruturada: false, texto, itens: [] };
                }
                const [, idPag, finalV, simV, tempV, visV] = matchPag;
                const pct = (v) => `${Math.round(Number(v) * 100)}%`;
                const numPag = this.numeroPaginaPorId(idPag);
                const itens = [
                    { rotulo: "Conf.", valor: pct(finalV) },
                    {
                        rotulo: "Princ.",
                        valor: numPag !== "?" ? `Pág. ${numPag}` : idPag,
                    },
                    { rotulo: "Texto", valor: pct(simV) },
                    { rotulo: "Temp.", valor: pct(tempV) },
                ];
                if (Number(visV) > 0) {
                    itens.push({ rotulo: "Visual", valor: pct(visV) });
                }
                const matchGamma = texto.match(/gamma_abs=([0-9.]+)/);
                if (matchGamma) {
                    itens.push({ rotulo: "Abst.", valor: pct(matchGamma[1]) });
                }
                return { ehEstruturada: true, texto, itens };
            },

            formatarTempo(segundos) {
                const total = Math.max(0, Math.floor(Number(segundos) || 0));
                const min = Math.floor(total / 60);
                const seg = total % 60;
                return `${String(min).padStart(2, "0")}:${String(seg).padStart(2, "0")}`;
            },

            aplicarVelocidadeAudio() {
                if (audioElInstancia) {
                    audioElInstancia.playbackRate = Number(this.velocidadeAudio) || 1;
                }
            },

            aoAtualizarTempoAudio() {
                if (!audioElInstancia || !this.documentoAtivo) {
                    return;
                }
                const tempo = audioElInstancia.currentTime;

                const seg = this.documentoAtivo.segmentos.find(
                    (s) => tempo >= s.inicio && tempo <= s.fim
                );
                this.segmentoAtivoId = seg ? seg.id_segmento : null;

                const inter = this.documentoAtivo.intervalos.find(
                    (i) => tempo >= i.inicio && tempo <= i.fim
                );
                if (!inter || inter.id_intervalo === this.intervaloAtivoId) {
                    return;
                }

                this.intervaloAtivoId = inter.id_intervalo;
                this._sincronizarFiltroComIntervalo(inter);
                this._rolarParaIntervalo(inter.id_intervalo);

                if (this.sincronizarAudioPdf) {
                    this._navegarPdfParaVinculo(inter.vinculo);
                }
            },

            _sincronizarFiltroComIntervalo(intervalo) {
                this.unidadeSelecionadaId = null;
                if (!this.paginaFiltroId) {
                    return;
                }
                const vinc = intervalo?.vinculo;
                if (vinc && !vinc.abstido && vinc.ids_paginas.length > 0) {
                    if (!vinc.ids_paginas.includes(this.paginaFiltroId)) {
                        this.paginaFiltroId = vinc.ids_paginas[0];
                    }
                } else {
                    this.paginaFiltroId = null;
                }
            },

            async selecionarIntervalo(intervalo, reproduzir = true, navegarPdf = true) {
                this.intervaloAtivoId = intervalo.id_intervalo;
                this._sincronizarFiltroComIntervalo(intervalo);
                this._rolarParaIntervalo(intervalo.id_intervalo);

                if (audioElInstancia && this.documentoAtivo?.url_audio) {
                    audioElInstancia.currentTime = intervalo.inicio;
                    if (reproduzir) {
                        try {
                            await audioElInstancia.play();
                        } catch {
                            // navegador pode bloquear autoplay se não houver gesto prévio
                        }
                    }
                }
                if (navegarPdf) {
                    await this._navegarPdfParaVinculo(intervalo.vinculo);
                } else {
                    this._sincronizarDestaquesPdf(intervalo.vinculo);
                }
            },

            async selecionarSegmento(segmento) {
                this.segmentoAtivoId = segmento.id_segmento;
                if (audioElInstancia && this.documentoAtivo?.url_audio) {
                    audioElInstancia.currentTime = segmento.inicio;
                    try {
                        await audioElInstancia.play();
                    } catch {
                        // ignora bloqueio de autoplay
                    }
                }
                const inter = this.documentoAtivo?.intervalos.find((i) =>
                    i.ids_segmentos.includes(segmento.id_segmento)
                );
                if (inter) {
                    this.intervaloAtivoId = inter.id_intervalo;
                    this._sincronizarFiltroComIntervalo(inter);
                    await this._navegarPdfParaVinculo(inter.vinculo);
                }
            },

            async _navegarPdfParaVinculo(vinculo) {
                if (!pdfViewerInstancia) {
                    return;
                }
                if (!vinculo || vinculo.abstido || !vinculo.ids_paginas.length) {
                    pdfViewerInstancia.destacarUnidades([]);
                    return;
                }
                const primeiraPag = this.mapaPaginasPorId.get(vinculo.ids_paginas[0]);
                if (
                    primeiraPag &&
                    Number(primeiraPag.numero_pagina) !== Number(this.paginaAtual)
                ) {
                    await pdfViewerInstancia.irParaPagina(
                        primeiraPag.numero_pagina,
                        false
                    );
                    this.paginaAtual = primeiraPag.numero_pagina;
                    this._atualizarUrl();
                }
                this._sincronizarDestaquesPdf(vinculo);
            },

            _sincronizarDestaquesPdf(vinculoExplicit = null) {
                if (!pdfViewerInstancia) {
                    return;
                }
                const interAtivo = this.documentoAtivo?.intervalos.find(
                    (i) => i.id_intervalo === this.intervaloAtivoId
                );
                const vinc = vinculoExplicit || interAtivo?.vinculo;
                if (!vinc || vinc.abstido) {
                    pdfViewerInstancia.destacarUnidades([], {
                        unidadeFocadaId: this.unidadeSelecionadaId,
                    });
                    return;
                }
                pdfViewerInstancia.destacarUnidades(vinc.ids_unidades, {
                    origem: vinc.origem,
                    unidadeFocadaId: this.unidadeSelecionadaId,
                });
            },

            unidadePossuiVinculo(idUnidade) {
                return (this.documentoAtivo?.intervalos || []).some(
                    (i) =>
                        i.vinculo &&
                        !i.vinculo.abstido &&
                        i.vinculo.ids_unidades.includes(idUnidade)
                );
            },

            async selecionarUnidadeNoPdf(unidade) {
                const intervalosDaUnidade = (
                    this.documentoAtivo?.intervalos || []
                ).filter(
                    (i) =>
                        i.vinculo &&
                        !i.vinculo.abstido &&
                        i.vinculo.ids_unidades.includes(unidade.id_unidade)
                );
                if (!intervalosDaUnidade.length) {
                    return;
                }

                this.unidadeSelecionadaId = unidade.id_unidade;
                this.paginaFiltroId = null;

                const alvo = intervalosDaUnidade[0];
                this.intervaloAtivoId = alvo.id_intervalo;
                this._rolarParaIntervalo(alvo.id_intervalo);
                if (audioElInstancia && this.documentoAtivo?.url_audio) {
                    audioElInstancia.currentTime = alvo.inicio;
                    try {
                        await audioElInstancia.play();
                    } catch {
                        // navegador pode bloquear autoplay se não houver gesto prévio
                    }
                }
                this._sincronizarDestaquesPdf(alvo.vinculo);
            },

            limparFiltros() {
                this.termoBusca = "";
                this.filtroOrigem = "todos";
                this.paginaFiltroId = null;
                this.unidadeSelecionadaId = null;
                this._atualizarUrl();
            },

            filtrarPorPaginaAtual() {
                if (!this.paginaAtualObj) {
                    return;
                }
                if (this.paginaFiltroId === this.paginaAtualObj.id_pagina) {
                    this.paginaFiltroId = null;
                } else {
                    this.paginaFiltroId = this.paginaAtualObj.id_pagina;
                    this.unidadeSelecionadaId = null;
                }
            },

            async irParaPagina(numeroPagina) {
                if (!pdfViewerInstancia) {
                    return;
                }
                await pdfViewerInstancia.irParaPagina(numeroPagina);
            },

            async alterarZoom(delta) {
                if (!pdfViewerInstancia) {
                    return;
                }
                this.zoomPdf = await pdfViewerInstancia.ajustarZoom(delta);
            },

            async ajustarZoomLargura() {
                if (!pdfViewerInstancia) {
                    return;
                }
                this.zoomPdf = await pdfViewerInstancia.ajustarLargura();
            },

            focarIntervaloAtivo() {
                if (this.intervaloAtivoId) {
                    this._rolarParaIntervalo(this.intervaloAtivoId);
                }
            },

            irParaAudioDaPaginaAtual() {
                const lista = this.intervalosDaPaginaAtual;
                if (!lista.length) {
                    return;
                }
                const idxAtual = lista.findIndex(
                    (i) => i.id_intervalo === this.intervaloAtivoId
                );
                const proximo =
                    idxAtual >= 0 ? lista[(idxAtual + 1) % lista.length] : lista[0];
                this.selecionarIntervalo(proximo, true, false);
            },

            _rolarParaIntervalo(idIntervalo) {
                const reduzirMovimento =
                    typeof window.matchMedia === "function" &&
                    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
                window.requestAnimationFrame(() => {
                    const el = document.querySelector(
                        `[data-intervalo-id="${idIntervalo}"]`
                    );
                    if (el) {
                        el.scrollIntoView({
                            block: "nearest",
                            behavior: reduzirMovimento ? "auto" : "smooth",
                        });
                    }
                });
            },

            unidadeEstaDestacada(idUnidade) {
                const inter = this.documentoAtivo?.intervalos.find(
                    (i) => i.id_intervalo === this.intervaloAtivoId
                );
                return Boolean(
                    inter?.vinculo &&
                        !inter.vinculo.abstido &&
                        inter.vinculo.ids_unidades.includes(idUnidade)
                );
            },

            abrirRevisao(intervalo) {
                if (this.revisaoAbertaId === intervalo.id_intervalo) {
                    this.revisaoAbertaId = null;
                    return;
                }
                const vinc = intervalo.vinculo;
                const ehTelemetria = Boolean(
                    this.resumoJustificativa(vinc)?.ehEstruturada
                );
                this.rascunhoRevisao = {
                    ids_paginas: vinc ? [...vinc.ids_paginas] : [],
                    ids_unidades: vinc ? [...vinc.ids_unidades] : [],
                    tipo_relacao: vinc?.tipo_relacao || "direct",
                    justificativa:
                        vinc && !ehTelemetria ? vinc.justificativa || "" : "",
                };
                this.revisaoAbertaId = intervalo.id_intervalo;
                this.unidadesAbertas = true;
            },

            vincularPaginaAtualAoRascunho() {
                const pag = this.paginaAtualObj;
                if (!pag) {
                    return;
                }
                if (!this.rascunhoRevisao.ids_paginas.includes(pag.id_pagina)) {
                    this.rascunhoRevisao.ids_paginas.push(pag.id_pagina);
                }
            },

            alternarUnidadeNoRascunho(unidade) {
                const idx = this.rascunhoRevisao.ids_unidades.indexOf(
                    unidade.id_unidade
                );
                if (idx >= 0) {
                    this.rascunhoRevisao.ids_unidades.splice(idx, 1);
                } else {
                    this.rascunhoRevisao.ids_unidades.push(unidade.id_unidade);
                    if (
                        !this.rascunhoRevisao.ids_paginas.includes(unidade.id_pagina)
                    ) {
                        this.rascunhoRevisao.ids_paginas.push(unidade.id_pagina);
                    }
                }
            },

            async _restaurarSnapshotVinculo(intervalo, snapshot) {
                if (!this.documentoAtivo || !snapshot) {
                    return;
                }
                this.salvandoRevisao = true;
                this.erroGeral = null;
                try {
                    const resp = await fetch(
                        `/api/documentos/${encodeURIComponent(this.documentoAtivo.id_documento)}/vinculos`,
                        {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                id_intervalo: intervalo.id_intervalo,
                                ids_paginas: snapshot.ids_paginas,
                                ids_unidades: snapshot.ids_unidades,
                                abster: snapshot.abstido,
                                tipo_relacao: snapshot.tipo_relacao || "direct",
                                justificativa: snapshot.justificativa || null,
                                id_aula: this.documentoAtivo.id_aula,
                            }),
                        }
                    );
                    const dados = await resp.json();
                    if (!resp.ok) {
                        this.erroGeral =
                            dados.detail || "Não foi possível desfazer a alteração.";
                        return;
                    }
                    intervalo.vinculo = dados;
                    this._registrarVinculoNaLista(dados);
                    this._sincronizarDestaquesPdf(dados);
                    await this.carregarAcervo();
                    this.exibirToast("Vínculo anterior restaurado.");
                } catch (erro) {
                    this.erroGeral = `Erro ao desfazer alteração: ${erro.message}`;
                } finally {
                    this.salvandoRevisao = false;
                }
            },

            async salvarRevisaoManual(intervalo) {
                if (!this.documentoAtivo) {
                    return;
                }
                this.salvandoRevisao = true;
                this.erroGeral = null;
                try {
                    const abster =
                        this.rascunhoRevisao.ids_paginas.length === 0 &&
                        this.rascunhoRevisao.ids_unidades.length === 0;
                    const resp = await fetch(
                        `/api/documentos/${encodeURIComponent(this.documentoAtivo.id_documento)}/vinculos`,
                        {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                id_intervalo: intervalo.id_intervalo,
                                ids_paginas: this.rascunhoRevisao.ids_paginas,
                                ids_unidades: this.rascunhoRevisao.ids_unidades,
                                abster,
                                tipo_relacao: this.rascunhoRevisao.tipo_relacao,
                                justificativa:
                                    this.rascunhoRevisao.justificativa || null,
                                id_aula: this.documentoAtivo.id_aula,
                            }),
                        }
                    );
                    const dados = await resp.json();
                    if (!resp.ok) {
                        this.erroGeral =
                            dados.detail || "Falha ao salvar revisão manual.";
                        return;
                    }
                    intervalo.vinculo = dados;
                    this._registrarVinculoNaLista(dados);
                    this.revisaoAbertaId = null;
                    this._sincronizarDestaquesPdf(dados);
                    await this.carregarAcervo();
                    this.exibirToast(
                        abster
                            ? `Intervalo #${intervalo.ordem} marcado como abstenção.`
                            : `Revisão salva no intervalo #${intervalo.ordem}.`
                    );
                } catch (erro) {
                    this.erroGeral = `Erro ao salvar revisão: ${erro.message}`;
                } finally {
                    this.salvandoRevisao = false;
                }
            },

            async marcarAbstencaoManual(intervalo) {
                if (!this.documentoAtivo) {
                    return;
                }
                const anterior = intervalo.vinculo
                    ? {
                          ids_paginas: [...(intervalo.vinculo.ids_paginas || [])],
                          ids_unidades: [...(intervalo.vinculo.ids_unidades || [])],
                          abstido: Boolean(intervalo.vinculo.abstido),
                          tipo_relacao: intervalo.vinculo.tipo_relacao,
                          justificativa: intervalo.vinculo.justificativa,
                      }
                    : null;

                this.salvandoRevisao = true;
                this.erroGeral = null;
                try {
                    const resp = await fetch(
                        `/api/documentos/${encodeURIComponent(this.documentoAtivo.id_documento)}/vinculos`,
                        {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                id_intervalo: intervalo.id_intervalo,
                                ids_paginas: [],
                                ids_unidades: [],
                                abster: true,
                                justificativa:
                                    "Abstenção definida manualmente na interface",
                                id_aula: this.documentoAtivo.id_aula,
                            }),
                        }
                    );
                    const dados = await resp.json();
                    if (!resp.ok) {
                        this.erroGeral =
                            dados.detail || "Falha ao registrar abstenção.";
                        return;
                    }
                    intervalo.vinculo = dados;
                    this._registrarVinculoNaLista(dados);
                    this.revisaoAbertaId = null;
                    this._sincronizarDestaquesPdf(dados);
                    await this.carregarAcervo();
                    this.exibirToast(
                        `Abstenção (∅) registrada no intervalo #${intervalo.ordem}.`,
                        anterior && !anterior.abstido
                            ? () => this._restaurarSnapshotVinculo(intervalo, anterior)
                            : null
                    );
                } catch (erro) {
                    this.erroGeral = `Erro ao marcar abstenção: ${erro.message}`;
                } finally {
                    this.salvandoRevisao = false;
                }
            },

            async removerAlvoVinculo(intervalo, alvo = {}) {
                if (!intervalo?.vinculo) {
                    return;
                }
                const anterior = {
                    ids_paginas: [...(intervalo.vinculo.ids_paginas || [])],
                    ids_unidades: [...(intervalo.vinculo.ids_unidades || [])],
                    abstido: Boolean(intervalo.vinculo.abstido),
                    tipo_relacao: intervalo.vinculo.tipo_relacao,
                    justificativa: intervalo.vinculo.justificativa,
                };
                this.salvandoRevisao = true;
                this.erroGeral = null;
                try {
                    const params = new URLSearchParams();
                    if (alvo.id_pagina) {
                        params.set("id_pagina", alvo.id_pagina);
                    }
                    if (alvo.id_unidade) {
                        params.set("id_unidade", alvo.id_unidade);
                    }
                    const sufixo = params.toString() ? `?${params.toString()}` : "";
                    const resp = await fetch(
                        `/api/vinculos/${encodeURIComponent(intervalo.vinculo.id_alinhamento)}${sufixo}`,
                        { method: "DELETE" }
                    );
                    const dados = await resp.json();
                    if (!resp.ok) {
                        this.erroGeral =
                            dados.detail || "Falha ao remover alvo do vínculo.";
                        return;
                    }
                    intervalo.vinculo = dados;
                    this._registrarVinculoNaLista(dados);
                    this._sincronizarDestaquesPdf(dados);
                    await this.carregarAcervo();
                    this.exibirToast(
                        alvo.id_pagina
                            ? "Página removida do vínculo."
                            : "Trecho removido do vínculo.",
                        () => this._restaurarSnapshotVinculo(intervalo, anterior)
                    );
                } catch (erro) {
                    this.erroGeral = `Erro ao remover vínculo: ${erro.message}`;
                } finally {
                    this.salvandoRevisao = false;
                }
            },
        };
    }

    function registrarStore() {
        if (!window.Alpine) {
            return;
        }
        if (!window.Alpine.store("anotai")) {
            window.Alpine.store("anotai", criarStoreAnotai());
        }
    }

    document.addEventListener("alpine:init", registrarStore);
    if (window.Alpine) {
        registrarStore();
    }
})();
