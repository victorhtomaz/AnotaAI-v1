(() => {
    "use strict";

    window.AnotaiWeb = window.AnotaiWeb || {};

    function criarModuloRevisao() {
        const { requisitarJson } = window.AnotaiWeb;

        function capturarSnapshot(vinculo) {
            if (!vinculo) {
                return null;
            }
            return {
                ids_paginas: [...(vinculo.ids_paginas || [])],
                ids_unidades: [...(vinculo.ids_unidades || [])],
                abstido: Boolean(vinculo.abstido),
                tipo_relacao: vinculo.tipo_relacao,
                justificativa: vinculo.justificativa,
            };
        }

        return {
            revisaoAbertaId: null,
            salvandoRevisao: false,
            rascunhoRevisao: {
                ids_paginas: [],
                ids_unidades: [],
                tipo_relacao: "direct",
                justificativa: "",
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

            async _executarMutacaoVinculo({
                url,
                metodo,
                corpo = null,
                idDocumentoAlvo,
                intervalo,
                mensagemErroPadrao,
                prefixoErroCatch,
                aoConcluir,
            }) {
                this.salvandoRevisao = true;
                this.erroGeral = null;
                try {
                    const opcoes = { method: metodo };
                    if (corpo !== null) {
                        opcoes.headers = { "Content-Type": "application/json" };
                        opcoes.body = JSON.stringify(corpo);
                    }
                    const { ok, dados } = await requisitarJson(url, opcoes);
                    if (!ok) {
                        this.erroGeral = dados.detail || mensagemErroPadrao;
                        return;
                    }
                    if (this.documentoAtivo?.id_documento === idDocumentoAlvo) {
                        const alvo =
                            this.documentoAtivo.intervalos.find(
                                (i) => i.id_intervalo === intervalo.id_intervalo
                            ) || intervalo;
                        alvo.vinculo = dados;
                        this._registrarVinculoNaLista(dados);
                        this._reconstruirIndiceVinculos();
                        this._sincronizarDestaquesPdf(dados);
                    }
                    await this.carregarAcervo();
                    aoConcluir?.(dados);
                } catch (erro) {
                    this.erroGeral = `${prefixoErroCatch}: ${erro.message}`;
                } finally {
                    this.salvandoRevisao = false;
                }
            },

            async _restaurarSnapshotVinculo(contextoOriginal, snapshot) {
                if (!contextoOriginal?.idDocumento || !snapshot) {
                    return;
                }
                await this._executarMutacaoVinculo({
                    url: `/api/documentos/${encodeURIComponent(contextoOriginal.idDocumento)}/vinculos`,
                    metodo: "POST",
                    corpo: {
                        id_intervalo: contextoOriginal.intervalo.id_intervalo,
                        ids_paginas: snapshot.ids_paginas,
                        ids_unidades: snapshot.ids_unidades,
                        abster: snapshot.abstido,
                        tipo_relacao: snapshot.tipo_relacao || "direct",
                        justificativa: snapshot.justificativa || null,
                        id_aula: contextoOriginal.idAula,
                    },
                    idDocumentoAlvo: contextoOriginal.idDocumento,
                    intervalo: contextoOriginal.intervalo,
                    mensagemErroPadrao: "Não foi possível desfazer a alteração.",
                    prefixoErroCatch: "Erro ao desfazer alteração",
                    aoConcluir: () => {
                        this.exibirToast("Vínculo anterior restaurado.");
                    },
                });
            },

            async salvarRevisaoManual(intervalo) {
                if (!this.documentoAtivo) {
                    return;
                }
                const idDocumento = this.documentoAtivo.id_documento;
                const abster =
                    this.rascunhoRevisao.ids_paginas.length === 0 &&
                    this.rascunhoRevisao.ids_unidades.length === 0;

                await this._executarMutacaoVinculo({
                    url: `/api/documentos/${encodeURIComponent(idDocumento)}/vinculos`,
                    metodo: "POST",
                    corpo: {
                        id_intervalo: intervalo.id_intervalo,
                        ids_paginas: this.rascunhoRevisao.ids_paginas,
                        ids_unidades: this.rascunhoRevisao.ids_unidades,
                        abster,
                        tipo_relacao: this.rascunhoRevisao.tipo_relacao,
                        justificativa: this.rascunhoRevisao.justificativa || null,
                        id_aula: this.documentoAtivo.id_aula,
                    },
                    idDocumentoAlvo: idDocumento,
                    intervalo,
                    mensagemErroPadrao: "Falha ao salvar revisão manual.",
                    prefixoErroCatch: "Erro ao salvar revisão",
                    aoConcluir: () => {
                        if (this.documentoAtivo?.id_documento === idDocumento) {
                            this.revisaoAbertaId = null;
                        }
                        this.exibirToast(
                            abster
                                ? `Intervalo #${intervalo.ordem} marcado como abstenção.`
                                : `Revisão salva no intervalo #${intervalo.ordem}.`
                        );
                    },
                });
            },

            async marcarAbstencaoManual(intervalo) {
                if (!this.documentoAtivo) {
                    return;
                }
                const contextoOriginal = {
                    idDocumento: this.documentoAtivo.id_documento,
                    idAula: this.documentoAtivo.id_aula,
                    intervalo,
                };
                const anterior = capturarSnapshot(intervalo.vinculo);

                await this._executarMutacaoVinculo({
                    url: `/api/documentos/${encodeURIComponent(contextoOriginal.idDocumento)}/vinculos`,
                    metodo: "POST",
                    corpo: {
                        id_intervalo: intervalo.id_intervalo,
                        ids_paginas: [],
                        ids_unidades: [],
                        abster: true,
                        justificativa: "Abstenção definida manualmente na interface",
                        id_aula: contextoOriginal.idAula,
                    },
                    idDocumentoAlvo: contextoOriginal.idDocumento,
                    intervalo,
                    mensagemErroPadrao: "Falha ao registrar abstenção.",
                    prefixoErroCatch: "Erro ao marcar abstenção",
                    aoConcluir: () => {
                        if (
                            this.documentoAtivo?.id_documento ===
                            contextoOriginal.idDocumento
                        ) {
                            this.revisaoAbertaId = null;
                        }
                        this.exibirToast(
                            `Abstenção (∅) registrada no intervalo #${intervalo.ordem}.`,
                            anterior && !anterior.abstido
                                ? () =>
                                      this._restaurarSnapshotVinculo(
                                          contextoOriginal,
                                          anterior
                                      )
                                : null
                        );
                    },
                });
            },

            async removerAlvoVinculo(intervalo, alvo = {}) {
                if (!intervalo?.vinculo || !this.documentoAtivo) {
                    return;
                }
                const contextoOriginal = {
                    idDocumento: this.documentoAtivo.id_documento,
                    idAula: this.documentoAtivo.id_aula,
                    intervalo,
                };
                const anterior = capturarSnapshot(intervalo.vinculo);

                const params = new URLSearchParams();
                if (alvo.id_pagina) {
                    params.set("id_pagina", alvo.id_pagina);
                }
                if (alvo.id_unidade) {
                    params.set("id_unidade", alvo.id_unidade);
                }
                const sufixo = params.toString() ? `?${params.toString()}` : "";

                await this._executarMutacaoVinculo({
                    url: `/api/vinculos/${encodeURIComponent(intervalo.vinculo.id_alinhamento)}${sufixo}`,
                    metodo: "DELETE",
                    corpo: null,
                    idDocumentoAlvo: contextoOriginal.idDocumento,
                    intervalo,
                    mensagemErroPadrao: "Falha ao remover alvo do vínculo.",
                    prefixoErroCatch: "Erro ao remover vínculo",
                    aoConcluir: () => {
                        this.exibirToast(
                            alvo.id_pagina
                                ? "Página removida do vínculo."
                                : "Trecho removido do vínculo.",
                            () =>
                                this._restaurarSnapshotVinculo(
                                    contextoOriginal,
                                    anterior
                                )
                        );
                    },
                });
            },
        };
    }

    window.AnotaiWeb.criarModuloRevisao = criarModuloRevisao;
})();
