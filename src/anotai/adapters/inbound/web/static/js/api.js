(() => {
    "use strict";

    window.AnotaiWeb = window.AnotaiWeb || {};

    /**
     * Executa fetch e faz parsing seguro de JSON com fallback para texto ou status HTTP,
     * evitando SyntaxError quando o servidor ou proxy retorna resposta não-JSON.
     */
    async function requisitarJson(url, opcoes = {}) {
        const resp = await fetch(url, opcoes);
        const contentType = resp.headers?.get?.("content-type") || "";
        let textoBruto = "";
        let dados = null;

        try {
            textoBruto = await resp.text();
            if (textoBruto) {
                dados = JSON.parse(textoBruto);
            }
        } catch {
            dados = null;
        }

        if (!dados || typeof dados !== "object") {
            const detalhe =
                textoBruto && !contentType.includes("text/html")
                    ? textoBruto.slice(0, 200).trim()
                    : `Erro HTTP ${resp.status}`;
            dados = { detail: detalhe || `Erro HTTP ${resp.status}` };
        }

        return { ok: resp.ok, status: resp.status, dados };
    }

    window.AnotaiWeb.requisitarJson = requisitarJson;
})();
