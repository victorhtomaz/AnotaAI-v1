(() => {
    "use strict";

    window.AnotaiWeb = window.AnotaiWeb || {};

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
            provedor_visual: "ollama",
            modelo_visual: "qwen3-vl:8b",
            temperatura_visual: 0.0,
            seed_visual: 42,
            pensar_visual: false,
            titulo_aula: "",
            provedor_transcricao: "whisperx",
            idioma_transcricao: "pt-BR",
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

    const metodosFormatacao = {
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

        formatarTempo(segundos) {
            const total = Math.max(0, Math.floor(Number(segundos) || 0));
            const min = Math.floor(total / 60);
            const seg = total % 60;
            return `${String(min).padStart(2, "0")}:${String(seg).padStart(2, "0")}`;
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

        rotuloEstrategiaAlinhamento(estrategia) {
            if (!estrategia) {
                return "";
            }
            const mapaLegado = {
                hierarchical_hmm: "Hierárquico · Sequencial",
                hierarchical: "Hierárquico",
                temporal_hmm: "Por página · Sequencial",
                temporal: "Por página",
                hybrid: "Híbrido (Lexical + Semântico)",
                bm25: "Lexical",
                embedding: "Semântico",
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
                    ? "Sequencial"
                    : temporal === "kernel"
                      ? "Vizinhança"
                      : temporal === "none"
                        ? "Sem temporal"
                        : temporal;
            const rotBase =
                base === "hybrid"
                    ? "Híbrido"
                    : base === "bm25"
                      ? "Lexical"
                      : base === "embedding"
                        ? "Semântico"
                        : base;
            return [rotEstrutural, rotTemporal, rotBase].filter(Boolean).join(" · ");
        },

        resumoJustificativa(vinculo) {
            if (Array.isArray(vinculo?.metricas) && vinculo.metricas.length > 0) {
                return {
                    ehEstruturada: true,
                    texto: (vinculo.justificativa || "").trim(),
                    itens: vinculo.metricas,
                };
            }
            const texto = (vinculo?.justificativa || "").trim();
            if (!texto) {
                return null;
            }
            return { ehEstruturada: false, texto, itens: [] };
        },
    };

    window.AnotaiWeb.fmtNumero2 = fmtNumero2;
    window.AnotaiWeb.criarOpcoesIniciais = criarOpcoesIniciais;
    window.AnotaiWeb.metodosFormatacao = metodosFormatacao;
})();
