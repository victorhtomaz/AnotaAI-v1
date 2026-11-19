(() => {
    "use strict";

    window.AnotaiWeb = window.AnotaiWeb || {};

    function criarModuloExplorador(contexto) {
        const { requisitarJson } = window.AnotaiWeb;

        return {
            carregandoDocumento: false,
            avisoPdf: null,
            unidadesAbertas: true,
            filtrosMobileAbertos: false,
            documentoAtivo: null,
            _reqDocumentoToken: 0,

            _mapaPaginas: new Map(),
            _mapaUnidades: new Map(),
            _mapaSegmentos: new Map(),
            _unidadesComVinculo: new Set(),

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

            _reconstruirIndicesDocumento() {
                const paginas = new Map();
                const unidades = new Map();
                const segmentos = new Map();

                if (this.documentoAtivo) {
                    for (const p of this.documentoAtivo.paginas || []) {
                        paginas.set(p.id_pagina, p);
                        for (const u of p.unidades || []) {
                            unidades.set(u.id_unidade, u);
                        }
                    }
                    for (const s of this.documentoAtivo.segmentos || []) {
                        segmentos.set(s.id_segmento, s);
                    }
                }

                this._mapaPaginas = paginas;
                this._mapaUnidades = unidades;
                this._mapaSegmentos = segmentos;
                this._reconstruirIndiceVinculos();
            },

            _reconstruirIndiceVinculos() {
                const vinculadas = new Set();
                for (const inter of this.documentoAtivo?.intervalos || []) {
                    const vinc = inter.vinculo;
                    if (vinc && !vinc.abstido) {
                        for (const uid of vinc.ids_unidades || []) {
                            vinculadas.add(uid);
                        }
                    }
                }
                this._unidadesComVinculo = vinculadas;
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
                this._reconstruirIndiceVinculos();
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

            conectarElementos(audioEl, pdfContainerEl) {
                if (audioEl) {
                    contexto.setAudioEl(audioEl);
                }
                if (pdfContainerEl && pdfContainerEl !== contexto.getPdfContainerEl()) {
                    contexto.setPdfContainerEl(pdfContainerEl);
                    const ViewerCls = window.PdfViewer;
                    if (typeof ViewerCls !== "function") {
                        return;
                    }
                    const viewer = new ViewerCls(pdfContainerEl, {
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
                    contexto.setPdfViewer(viewer);
                    if (this.documentoAtivo) {
                        viewer.carregarDocumento(
                            this.documentoAtivo.url_pdf,
                            this.documentoAtivo.paginas
                        );
                    }
                }
            },

            async abrirDocumento(idDocumento, idAula = null, trocarAba = true) {
                const token = ++this._reqDocumentoToken;
                if (this.toast?.desfazer) {
                    this.fecharToast();
                }
                if (!idDocumento) {
                    this.documentoAtivo = null;
                    this._reconstruirIndicesDocumento();
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
                    const { ok, dados } = await requisitarJson(
                        `/api/documentos/${encodeURIComponent(idDocumento)}${query}`
                    );
                    if (token !== this._reqDocumentoToken) {
                        return;
                    }
                    if (!ok) {
                        this.erroGeral =
                            dados.detail || "Não foi possível carregar o documento.";
                        return;
                    }

                    this.documentoAtivo = dados;
                    this._reconstruirIndicesDocumento();

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
                    if (token !== this._reqDocumentoToken) {
                        return;
                    }

                    const pdfViewerInstancia = contexto.getPdfViewer();
                    if (pdfViewerInstancia) {
                        await pdfViewerInstancia.carregarDocumento(
                            dados.url_pdf,
                            dados.paginas
                        );
                        if (token !== this._reqDocumentoToken) {
                            return;
                        }
                        this.zoomPdf = pdfViewerInstancia.zoom;
                        this._sincronizarDestaquesPdf();
                    }
                } catch (erro) {
                    if (token === this._reqDocumentoToken) {
                        this.erroGeral = `Erro ao carregar documento: ${erro.message}`;
                    }
                } finally {
                    if (token === this._reqDocumentoToken) {
                        this.carregandoDocumento = false;
                    }
                }
            },

            get mapaPaginasPorId() {
                return this._mapaPaginas;
            },

            get mapaUnidadesPorId() {
                return this._mapaUnidades;
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
                        const pagUnidade = this._mapaUnidades.get(unidFiltro)?.id_pagina;
                        const mesmoPag =
                            vinc &&
                            pagUnidade &&
                            vinc.ids_paginas.includes(pagUnidade);
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
                            const pag = this._mapaPaginas.get(pid);
                            if (pag && `página ${pag.numero_pagina}`.includes(termo)) {
                                return true;
                            }
                        }
                        for (const uid of vinc.ids_unidades) {
                            const unid = this._mapaUnidades.get(uid);
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
                const resultado = [];
                for (const idSeg of intervalo.ids_segmentos) {
                    const seg = this._mapaSegmentos.get(idSeg);
                    if (seg) {
                        resultado.push(seg);
                    }
                }
                return resultado;
            },

            numeroPaginaPorId(idPagina) {
                return this._mapaPaginas.get(idPagina)?.numero_pagina || "?";
            },

            rotuloTipoUnidade(tipo) {
                if (typeof window.traduzirTipoUnidade === "function") {
                    return window.traduzirTipoUnidade(tipo);
                }
                return tipo || "Unidade";
            },

            descricaoUnidadePorId(idUnidade) {
                const u = this._mapaUnidades.get(idUnidade);
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
                const unid = this._mapaUnidades.get(idUnidade);
                if (unid && Number(unid.numero_pagina) !== Number(this.paginaAtual)) {
                    await this.irParaPagina(unid.numero_pagina);
                }
                this.intervaloAtivoId = intervalo.id_intervalo;
                this.unidadeSelecionadaId = idUnidade;
                this._sincronizarDestaquesPdf(intervalo.vinculo);
            },

            aplicarVelocidadeAudio() {
                const audioElInstancia = contexto.getAudioEl();
                if (audioElInstancia) {
                    audioElInstancia.playbackRate = Number(this.velocidadeAudio) || 1;
                }
            },

            aoAtualizarTempoAudio() {
                const audioElInstancia = contexto.getAudioEl();
                if (!audioElInstancia || !this.documentoAtivo) {
                    return;
                }
                const tempo = audioElInstancia.currentTime;

                const seg = this.documentoAtivo.segmentos.find(
                    (s) => tempo >= s.inicio && tempo <= s.fim
                );
                const novoSegId = seg ? seg.id_segmento : null;
                if (novoSegId !== this.segmentoAtivoId) {
                    this.segmentoAtivoId = novoSegId;
                }

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

                const audioElInstancia = contexto.getAudioEl();
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
                const audioElInstancia = contexto.getAudioEl();
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
                const pdfViewerInstancia = contexto.getPdfViewer();
                if (!pdfViewerInstancia) {
                    return;
                }
                if (!vinculo || vinculo.abstido || !vinculo.ids_paginas.length) {
                    pdfViewerInstancia.destacarUnidades([]);
                    return;
                }
                const primeiraPag = this._mapaPaginas.get(vinculo.ids_paginas[0]);
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
                const pdfViewerInstancia = contexto.getPdfViewer();
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
                return this._unidadesComVinculo.has(idUnidade);
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

                const audioElInstancia = contexto.getAudioEl();
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
                const pdfViewerInstancia = contexto.getPdfViewer();
                if (!pdfViewerInstancia) {
                    return;
                }
                await pdfViewerInstancia.irParaPagina(numeroPagina);
            },

            async alterarZoom(delta) {
                const pdfViewerInstancia = contexto.getPdfViewer();
                if (!pdfViewerInstancia) {
                    return;
                }
                this.zoomPdf = await pdfViewerInstancia.ajustarZoom(delta);
            },

            async ajustarZoomLargura() {
                const pdfViewerInstancia = contexto.getPdfViewer();
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
        };
    }

    window.AnotaiWeb.criarModuloExplorador = criarModuloExplorador;
})();
