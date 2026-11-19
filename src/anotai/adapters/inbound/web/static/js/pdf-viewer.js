(() => {
    "use strict";

    const TIPOS_UNIDADE_PT = {
        title: "Título",
        section_header: "Seção",
        paragraph: "Parágrafo",
        list_item: "Item",
        table: "Tabela",
        figure: "Figura",
        caption: "Legenda",
        equation: "Equação",
        code: "Código",
        header: "Cabeçalho",
        footer: "Rodapé",
    };

    function traduzirTipoUnidade(tipo) {
        return TIPOS_UNIDADE_PT[tipo] || tipo || "Unidade";
    }

    window.traduzirTipoUnidade = traduzirTipoUnidade;

    let _pdfjsLibCache = null;

    async function obterPdfJs() {
        if (_pdfjsLibCache) {
            return _pdfjsLibCache;
        }
        const lib = await import("/static/vendor/pdf.min.mjs?v=4.10.38");
        if (lib?.GlobalWorkerOptions) {
            lib.GlobalWorkerOptions.workerSrc = "/static/vendor/pdf.worker.min.mjs?v=4.10.38";
        }
        _pdfjsLibCache = lib;
        return lib;
    }

    class PdfViewer {
    /**
     * Encapsula a renderização do PDF via PDF.js, zoom, camada de texto
     * e overlay interativo de CaixaDelimitadora com coordenadas em %.
     */
    constructor(containerEl, callbacks = {}) {
        this.containerEl = containerEl;
        this.callbacks = callbacks;
        this.pdfDoc = null;
        this.urlPdf = null;
        this.paginasMeta = [];
        this.mapaPaginas = new Map();
        this.paginaAtual = 1;
        this.zoom = 1.0;
        this.modoFallback = false;
        this.idsDestacadas = new Set();
        this.origemDestaque = null;
        this.unidadeFocadaId = null;
        this._renderToken = 0;
        this._renderTask = null;

        this._garantirEstruturaDOM();
    }

    _garantirEstruturaDOM() {
        if (!this.containerEl) {
            return;
        }
        this.containerEl.innerHTML = "";

        this.stageEl = document.createElement("div");
        this.stageEl.className = "pdf-stage";

        this.canvasEl = document.createElement("canvas");
        this.canvasEl.className = "pdf-canvas";

        this.imgFallbackEl = document.createElement("img");
        this.imgFallbackEl.className = "pdf-fallback-img";
        this.imgFallbackEl.alt = "Página renderizada do documento PDF";
        this.imgFallbackEl.hidden = true;

        this.textLayerEl = document.createElement("div");
        this.textLayerEl.className = "pdf-text-layer textLayer";

        this.overlayLayerEl = document.createElement("div");
        this.overlayLayerEl.className = "pdf-overlay-layer";

        this.fallbackNoticeEl = document.createElement("div");
        this.fallbackNoticeEl.className = "pdf-fallback-aviso";
        this.fallbackNoticeEl.hidden = true;

        this.stageEl.append(
            this.canvasEl,
            this.imgFallbackEl,
            this.textLayerEl,
            this.overlayLayerEl,
            this.fallbackNoticeEl
        );
        this.containerEl.appendChild(this.stageEl);
    }

    get totalPaginas() {
        if (this.pdfDoc && typeof this.pdfDoc.numPages === "number") {
            return this.pdfDoc.numPages;
        }
        return this.paginasMeta.length;
    }

    async carregarDocumento(urlPdf, paginasMetadados = []) {
        this.urlPdf = urlPdf || null;
        this.paginasMeta = Array.isArray(paginasMetadados) ? paginasMetadados : [];
        this.mapaPaginas.clear();
        for (const pag of this.paginasMeta) {
            this.mapaPaginas.set(Number(pag.numero_pagina), pag);
        }

        if (this.pdfDoc && typeof this.pdfDoc.destroy === "function") {
            try {
                await this.pdfDoc.destroy();
            } catch {
                // ignora erro ao encerrar instância anterior
            }
        }
        this.pdfDoc = null;
        this.modoFallback = false;
        this.paginaAtual = 1;
        this.zoom = this._calcularZoomInicial(this.mapaPaginas.get(1));

        if (urlPdf) {
            try {
                const pdfjsLib = await obterPdfJs();
                if (typeof pdfjsLib?.getDocument === "function") {
                    const loadingTask = pdfjsLib.getDocument(urlPdf);
                    this.pdfDoc = await loadingTask.promise;
                } else {
                    this.modoFallback = true;
                }
            } catch (erro) {
                this.modoFallback = true;
                const detalhe = erro?.message || String(erro || "erro desconhecido");
                this.callbacks.onErro?.(
                    `Visualização vetorial indisponível (${detalhe}); exibindo mapa estrutural das unidades.`
                );
                console.warn("Fallback estrutural ativado no PdfViewer:", erro);
            }
        } else {
            this.modoFallback = true;
        }

        await this.irParaPagina(1, false);
    }

    async irParaPagina(numeroPagina, notificar = true) {
        const total = Math.max(1, this.totalPaginas);
        const alvo = Math.max(1, Math.min(total, Number(numeroPagina) || 1));
        this.paginaAtual = alvo;
        await this._renderizarPaginaAtual();
        if (notificar) {
            this.callbacks.onChangePagina?.(this.paginaAtual);
        }
    }

    async definirZoom(novaEscala) {
        const ajustado = Math.max(0.25, Math.min(2.5, Number(novaEscala) || 1.0));
        this.zoom = Math.round(ajustado * 100) / 100;
        await this._renderizarPaginaAtual();
        return this.zoom;
    }

    async ajustarZoom(delta) {
        return this.definirZoom(this.zoom + delta);
    }

    async ajustarLargura() {
        const paginaMeta = this.mapaPaginas.get(this.paginaAtual);
        const novaEscala = this._calcularZoomInicial(paginaMeta);
        return this.definirZoom(novaEscala);
    }

    destacarUnidades(idsUnidades = [], metadados = {}) {
        this.idsDestacadas = new Set(Array.isArray(idsUnidades) ? idsUnidades : []);
        this.origemDestaque = metadados.origem || null;
        this.unidadeFocadaId = metadados.unidadeFocadaId || null;
        this._atualizarEstilosOverlays();
    }

    _calcularZoomInicial(paginaMeta) {
        const larguraPag = paginaMeta?.largura || 612;
        const alturaPag = paginaMeta?.altura || 792;
        const wrapper = this.containerEl?.parentElement;
        const estilo = wrapper ? window.getComputedStyle(wrapper) : null;
        const padX = estilo
            ? parseFloat(estilo.paddingLeft) + parseFloat(estilo.paddingRight) + 8
            : 40;
        const padY = estilo
            ? parseFloat(estilo.paddingTop) + parseFloat(estilo.paddingBottom) + 8
            : 40;
        const larguraDisp =
            (wrapper?.clientWidth || Math.round(window.innerWidth * 0.52)) - padX;
        const alturaDisp =
            (wrapper?.clientHeight || Math.round(window.innerHeight * 0.68)) - padY;
        if (larguraDisp <= 100) {
            return 0.85;
        }
        const escalaLargura = larguraDisp / larguraPag;
        const escalaAltura = alturaDisp > 100 ? alturaDisp / alturaPag : escalaLargura;
        const escala = Math.min(escalaLargura, escalaAltura);
        return Math.max(0.25, Math.min(1.5, Math.floor(escala * 100) / 100));
    }

    _urlImagemPagina(numeroPagina) {
        if (!this.urlPdf) {
            return null;
        }
        return `${this.urlPdf.replace(/\/pdf$/, "")}/paginas/${numeroPagina}/imagem`;
    }

    _canvasEstaEmBranco(ctx) {
        try {
            const w = this.canvasEl.width;
            const h = this.canvasEl.height;
            if (!w || !h) {
                return true;
            }
            const passos = 6;
            for (let ix = 1; ix < passos; ix++) {
                for (let iy = 1; iy < passos; iy++) {
                    const x = Math.floor((w * ix) / passos);
                    const y = Math.floor((h * iy) / passos);
                    const px = ctx.getImageData(x, y, 1, 1).data;
                    if (px[3] > 0 && (px[0] < 252 || px[1] < 252 || px[2] < 252)) {
                        return false;
                    }
                }
            }
            return true;
        } catch {
            return false;
        }
    }

    async _renderizarPaginaAtual() {
        if (!this.stageEl) {
            return;
        }
        if (this._renderTask && typeof this._renderTask.cancel === "function") {
            try {
                this._renderTask.cancel();
            } catch {
                // ignora cancelamento anterior
            }
            this._renderTask = null;
        }

        const token = ++this._renderToken;
        const paginaMeta = this.mapaPaginas.get(this.paginaAtual) || {
            numero_pagina: this.paginaAtual,
            largura: 612,
            altura: 792,
            unidades: [],
        };

        let larguraPx = Math.round((paginaMeta.largura || 612) * this.zoom);
        let alturaPx = Math.round((paginaMeta.altura || 792) * this.zoom);

        this.textLayerEl.innerHTML = "";
        this.fallbackNoticeEl.hidden = true;
        this.imgFallbackEl.hidden = true;
        this.imgFallbackEl.style.display = "none";
        this.canvasEl.hidden = false;
        this.canvasEl.style.display = "block";

        if (this.pdfDoc && !this.modoFallback) {
            try {
                const page = await this.pdfDoc.getPage(this.paginaAtual);
                if (token !== this._renderToken) {
                    return;
                }
                const viewport = page.getViewport({ scale: this.zoom });
                larguraPx = Math.round(viewport.width);
                alturaPx = Math.round(viewport.height);

                const dpr = window.devicePixelRatio || 1;
                this.canvasEl.width = Math.round(viewport.width * dpr);
                this.canvasEl.height = Math.round(viewport.height * dpr);
                this.canvasEl.style.width = `${larguraPx}px`;
                this.canvasEl.style.height = `${alturaPx}px`;

                const ctx = this.canvasEl.getContext("2d");
                if (ctx) {
                    ctx.clearRect(0, 0, this.canvasEl.width, this.canvasEl.height);
                    const transform = dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined;
                    const task = page.render({ canvasContext: ctx, viewport, transform });
                    this._renderTask = task;
                    await task.promise;
                    this._renderTask = null;

                    if (token !== this._renderToken) {
                        return;
                    }
                    if (this._canvasEstaEmBranco(ctx)) {
                        this._ativarImagemServidor(paginaMeta, larguraPx, alturaPx);
                    }
                }
                if (token !== this._renderToken) {
                    return;
                }
                await this._renderizarCamadaTexto(page, viewport, token);
            } catch (erro) {
                if (erro?.name === "RenderingCancelledException") {
                    return;
                }
                console.warn("Falha ao renderizar página no PDF.js, usando imagem do servidor:", erro);
                this._ativarImagemServidor(paginaMeta, larguraPx, alturaPx);
            }
        } else {
            this._ativarImagemServidor(paginaMeta, larguraPx, alturaPx);
        }

        if (token !== this._renderToken) {
            return;
        }

        this.stageEl.style.width = `${larguraPx}px`;
        this.stageEl.style.height = `${alturaPx}px`;
        this.textLayerEl.style.width = `${larguraPx}px`;
        this.textLayerEl.style.height = `${alturaPx}px`;
        this.overlayLayerEl.style.width = `${larguraPx}px`;
        this.overlayLayerEl.style.height = `${alturaPx}px`;

        this._renderizarOverlays(paginaMeta);
    }

    _ativarImagemServidor(paginaMeta, larguraPx, alturaPx) {
        const urlImg = this._urlImagemPagina(paginaMeta.numero_pagina);
        if (urlImg) {
            this.canvasEl.hidden = true;
            this.canvasEl.style.display = "none";
            this.imgFallbackEl.hidden = false;
            this.imgFallbackEl.style.display = "block";
            this.imgFallbackEl.style.width = `${larguraPx}px`;
            this.imgFallbackEl.style.height = `${alturaPx}px`;
            if (this.imgFallbackEl.getAttribute("src") !== urlImg) {
                this.imgFallbackEl.src = urlImg;
            }
            this.imgFallbackEl.onerror = () => {
                this.imgFallbackEl.hidden = true;
                this.imgFallbackEl.style.display = "none";
                this.canvasEl.hidden = false;
                this.canvasEl.style.display = "block";
                this._renderizarCanvasFallback(larguraPx, alturaPx, paginaMeta);
            };
            return;
        }
        this._renderizarCanvasFallback(larguraPx, alturaPx, paginaMeta);
    }

    _renderizarCanvasFallback(larguraPx, alturaPx, paginaMeta) {
        this.canvasEl.width = larguraPx;
        this.canvasEl.height = alturaPx;
        this.canvasEl.style.width = `${larguraPx}px`;
        this.canvasEl.style.height = `${alturaPx}px`;

        const ctx = this.canvasEl.getContext("2d");
        if (ctx) {
            ctx.fillStyle = "#f8f8f6";
            ctx.fillRect(0, 0, larguraPx, alturaPx);
            ctx.strokeStyle = "#bfc8c9";
            ctx.lineWidth = 1;
            ctx.strokeRect(0.5, 0.5, larguraPx - 1, alturaPx - 1);
        }

        this.fallbackNoticeEl.hidden = false;
        this.fallbackNoticeEl.textContent =
            `Página ${paginaMeta.numero_pagina} — mapa estrutural das unidades`;
    }

    async _renderizarCamadaTexto(page, viewport, token) {
        try {
            const pdfjsLib = await obterPdfJs();
            const textContent = await page.getTextContent();
            if (token !== this._renderToken) {
                return;
            }
            if (typeof pdfjsLib?.TextLayer === "function") {
                const textLayer = new pdfjsLib.TextLayer({
                    textContentSource: textContent,
                    container: this.textLayerEl,
                    viewport,
                });
                await textLayer.render();
            } else if (typeof pdfjsLib?.renderTextLayer === "function") {
                const task = pdfjsLib.renderTextLayer({
                    textContentSource: textContent,
                    container: this.textLayerEl,
                    viewport,
                });
                if (task?.promise) {
                    await task.promise;
                }
            }
        } catch {
            // seleção de texto é progressiva; nunca impede os overlays
        }
    }

    _renderizarOverlays(paginaMeta) {
        this.overlayLayerEl.innerHTML = "";
        const unidades = Array.isArray(paginaMeta.unidades) ? paginaMeta.unidades : [];

        const svgNS = "http://www.w3.org/2000/svg";
        const svgEl = document.createElementNS(svgNS, "svg");
        svgEl.setAttribute("class", "pdf-svg-guides");
        svgEl.setAttribute("viewBox", "0 0 100 100");
        svgEl.setAttribute("preserveAspectRatio", "none");
        svgEl.setAttribute("aria-hidden", "true");

        for (const unidade of unidades) {
            if (!unidade.caixa) {
                continue;
            }
            const { x_pct, y_pct, w_pct, h_pct } = unidade.caixa;

            const rect = document.createElementNS(svgNS, "rect");
            rect.setAttribute("x", String(x_pct));
            rect.setAttribute("y", String(y_pct));
            rect.setAttribute("width", String(w_pct));
            rect.setAttribute("height", String(h_pct));
            rect.setAttribute("data-unidade-id", unidade.id_unidade);
            rect.setAttribute("class", "pdf-svg-rect");
            svgEl.appendChild(rect);

            const botao = document.createElement("button");
            botao.type = "button";
            botao.className = "pdf-bbox-item";
            botao.dataset.unidadeId = unidade.id_unidade;
            botao.style.left = `${x_pct}%`;
            botao.style.top = `${y_pct}%`;
            botao.style.width = `${w_pct}%`;
            botao.style.height = `${h_pct}%`;

            const tipoPt = traduzirTipoUnidade(unidade.tipo);
            const resumoTexto = unidade.texto ? unidade.texto.slice(0, 120) : "Unidade visual";
            botao.title = `[${tipoPt} #${unidade.ordem_leitura}] ${resumoTexto}`;
            botao.setAttribute(
                "aria-label",
                `Unidade ${unidade.ordem_leitura} (${tipoPt}) na página ${paginaMeta.numero_pagina}: ${resumoTexto}`
            );

            const etiqueta = document.createElement("span");
            etiqueta.className = "pdf-bbox-etiqueta";
            etiqueta.textContent = `${tipoPt} #${unidade.ordem_leitura}`;
            botao.appendChild(etiqueta);

            botao.addEventListener("click", (ev) => {
                ev.stopPropagation();
                this.callbacks.onClickUnidade?.(unidade);
            });

            this.overlayLayerEl.appendChild(botao);
        }

        this.overlayLayerEl.prepend(svgEl);
        this._atualizarEstilosOverlays();
    }

    _atualizarEstilosOverlays() {
        if (!this.overlayLayerEl) {
            return;
        }
        const itens = this.overlayLayerEl.querySelectorAll("[data-unidade-id]");
        itens.forEach((el) => {
            const idUnidade = el.getAttribute("data-unidade-id");
            const destacada = idUnidade ? this.idsDestacadas.has(idUnidade) : false;
            const focada = Boolean(idUnidade && idUnidade === this.unidadeFocadaId);

            el.classList.toggle("is-highlighted", destacada);
            el.classList.toggle("is-focused", focada);
            el.classList.toggle(
                "is-manual",
                destacada && this.origemDestaque === "manual"
            );
            el.classList.toggle(
                "is-automatic",
                destacada && this.origemDestaque !== "manual"
            );
        });
    }
}

window.PdfViewer = PdfViewer;
})();
