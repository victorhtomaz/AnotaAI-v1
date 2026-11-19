(() => {
    "use strict";

    window.AnotaiWeb = window.AnotaiWeb || {};

    function criarModuloImportacao() {
        const { criarOpcoesIniciais, fmtNumero2, requisitarJson } = window.AnotaiWeb;

        return {
            carregandoAcervo: false,
            submetendoProcessamento: false,
            cancelandoJob: false,
            confirmandoCancelamento: false,
            erroImportacao: null,
            filtroAcervo: "vinculados",

            opcoes: criarOpcoesIniciais(),
            opcoesPadrao: criarOpcoesIniciais(),
            idDocumentoExistente: "",
            idAulaExistente: "",
            nomeArquivoPdf: "",
            nomeArquivoAudio: "",

            jobAtual: null,
            _pollingTimer: null,
            _pollingJobIdAtivo: null,

            documentos: [],
            aulas: [],

            get documentosVinculados() {
                return this.documentos.filter((doc) => Boolean(doc.id_aula));
            },

            get documentosAcervoVisiveis() {
                return this.filtroAcervo === "todos"
                    ? this.documentos
                    : this.documentosVinculados;
            },

            async carregarOpcoesPadrao() {
                try {
                    const { ok, dados } = await requisitarJson("/api/opcoes-padrao");
                    if (!ok) {
                        return;
                    }
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
                    formEl.querySelectorAll('input[type="file"]').forEach((input) => {
                        input.value = "";
                    });
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
                        estrategia: "embedding",
                        base: "embedding",
                        temporal: "kernel",
                    },
                    lexical: {
                        estrategia: "bm25",
                        base: "bm25",
                        temporal: "kernel",
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
                    const [resDocs, resAulas] = await Promise.all([
                        requisitarJson("/api/documentos"),
                        requisitarJson("/api/aulas"),
                    ]);
                    if (resDocs.ok && Array.isArray(resDocs.dados)) {
                        this.documentos = resDocs.dados;
                    }
                    if (resAulas.ok && Array.isArray(resAulas.dados)) {
                        this.aulas = resAulas.dados;
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
                    const { ok, dados } = await requisitarJson("/api/documentos", {
                        method: "POST",
                        body: formData,
                    });
                    if (!ok) {
                        this.erroImportacao =
                            dados.detail || "Não foi possível iniciar o processamento.";
                        window.requestAnimationFrame(() => {
                            document.getElementById("alerta-erro-importacao")?.focus();
                        });
                        return;
                    }
                    this._pollingJobIdAtivo = dados.job_id;
                    await this._consultarStatusJob(dados.job_id);
                    this._agendarProximoPolling(dados.job_id);
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
                this._pollingJobIdAtivo = jobId;
                this._agendarProximoPolling(jobId);
            },

            _agendarProximoPolling(jobId) {
                if (this._pollingTimer !== null) {
                    window.clearTimeout(this._pollingTimer);
                    this._pollingTimer = null;
                }
                if (
                    this._pollingJobIdAtivo !== jobId ||
                    !this.jobAtual?.em_andamento
                ) {
                    return;
                }
                this._pollingTimer = window.setTimeout(async () => {
                    this._pollingTimer = null;
                    if (this._pollingJobIdAtivo !== jobId) {
                        return;
                    }
                    await this._consultarStatusJob(jobId);
                    this._agendarProximoPolling(jobId);
                }, 1500);
            },

            _pararPolling() {
                this._pollingJobIdAtivo = null;
                if (this._pollingTimer !== null) {
                    window.clearTimeout(this._pollingTimer);
                    this._pollingTimer = null;
                }
            },

            async _consultarStatusJob(jobId) {
                try {
                    const { ok, dados } = await requisitarJson(
                        `/api/jobs/${encodeURIComponent(jobId)}`
                    );
                    if (!ok) {
                        if (this._pollingJobIdAtivo === jobId) {
                            this._pararPolling();
                        }
                        return;
                    }
                    if (this._pollingJobIdAtivo !== jobId) {
                        return;
                    }
                    this.jobAtual = dados;
                    if (!dados.em_andamento) {
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
                    const { ok, dados } = await requisitarJson(
                        `/api/jobs/${encodeURIComponent(this.jobAtual.job_id)}/cancelar`,
                        { method: "POST" }
                    );
                    if (ok) {
                        this.jobAtual = dados;
                        this._pararPolling();
                        await this.carregarAcervo();
                        this.exibirToast("Processamento interrompido.");
                    } else {
                        this.erroImportacao =
                            dados.detail || "Não foi possível interromper o processamento.";
                    }
                } catch (erro) {
                    this.erroImportacao = `Falha ao interromper processamento: ${erro.message}`;
                } finally {
                    this.cancelandoJob = false;
                }
            },
        };
    }

    window.AnotaiWeb.criarModuloImportacao = criarModuloImportacao;
})();
