(() => {
    "use strict";

    function mesclarComGetters(destino, ...fontes) {
        for (const fonte of fontes) {
            if (fonte) {
                Object.defineProperties(
                    destino,
                    Object.getOwnPropertyDescriptors(fonte)
                );
            }
        }
        return destino;
    }

    function criarStoreAnotai() {
        const ehMac =
            typeof navigator !== "undefined" &&
            /Mac|iPhone|iPad|iPod/i.test(
                navigator.platform || navigator.userAgent || ""
            );

        // Instâncias externas mantidas fora da reatividade do Alpine (Proxy quebra #private fields do PDF.js)
        let pdfViewerInstancia = null;
        let audioElInstancia = null;
        let pdfContainerElInstancia = null;

        const contextoMidia = {
            getPdfViewer: () => pdfViewerInstancia,
            setPdfViewer: (v) => {
                pdfViewerInstancia = v;
            },
            getAudioEl: () => audioElInstancia,
            setAudioEl: (el) => {
                audioElInstancia = el;
            },
            getPdfContainerEl: () => pdfContainerElInstancia,
            setPdfContainerEl: (el) => {
                pdfContainerElInstancia = el;
            },
        };

        const {
            metodosFormatacao,
            criarModuloImportacao,
            criarModuloExplorador,
            criarModuloRevisao,
        } = window.AnotaiWeb;

        const base = {
            abaAtiva: "importacao",
            erroGeral: null,
            atalhoBusca: ehMac ? "⌘K" : "Ctrl+K",
            toast: null,
            _toastTimer: null,
            _atalhosRegistrados: false,

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
        };

        return mesclarComGetters(
            base,
            metodosFormatacao,
            criarModuloImportacao(),
            criarModuloExplorador(contextoMidia),
            criarModuloRevisao()
        );
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
