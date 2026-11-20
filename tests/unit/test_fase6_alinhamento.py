import math
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anotai.adapters.inbound.cli.comando_alinhar import executar_comando_alinhar
from anotai.adapters.inbound.cli.principal import main
from anotai.adapters.outbound.persistence import (
    RepositorioAlinhamentoSQLite,
    RepositorioAulaSQLite,
    RepositorioDocumentoSQLite,
)
from anotai.adapters.outbound.search import IndiceBM25
from anotai.application.use_cases.alinhar_aula import AlinharAula
from anotai.application.use_cases.recuperar_candidatos import RecuperarCandidatos
from anotai.config import Settings
from anotai.domain.entities import (
    Aula,
    Documento,
    IntervaloExplicativo,
    PaginaDocumento,
    SegmentoTranscricao,
    UnidadeDocumento,
)
from anotai.domain.value_objects import (
    CaixaDelimitadora,
    CandidatoPagina,
    CandidatoUnidade,
    IntervaloTempo,
    MetadadosAudio,
    OrigemAlinhamento,
    ParametrosHMM,
    PesosAlinhamento,
    ProvenienciaDocumento,
    ResultadoRecuperacaoIntervalo,
    StatusAlinhamento,
    calcular_contexto_temporal_pagina,
    calcular_evidencia_visual_pagina,
    calcular_posteriores_hmm,
    combinar_sinais_alinhamento,
)


def _criar_documento_fase6(id_doc: str = "doc-f6") -> Documento:
    unidades_p1 = [
        UnidadeDocumento(
            id_unidade=f"{id_doc}-p1-u1",
            id_documento=id_doc,
            id_pagina=f"{id_doc}-p1",
            tipo="title",
            texto="Redes Neurais Convolucionais e Filtros Espaciais",
            ordem_leitura=1,
            caixa=CaixaDelimitadora(10.0, 10.0, 200.0, 30.0),
            fonte="native",
            ids_evidencias=["ev-nativa-p1-u1"],
        ),
        UnidadeDocumento(
            id_unidade=f"{id_doc}-p1-u2",
            id_documento=id_doc,
            id_pagina=f"{id_doc}-p1",
            tipo="figure",
            texto="Diagrama da convolução 2D com stride e padding sobre matriz de pixels",
            ordem_leitura=2,
            caixa=CaixaDelimitadora(10.0, 40.0, 300.0, 150.0),
            fonte="ollama",
            ids_evidencias=["ev-ocr-p1-u2"],
        ),
    ]
    unidades_p2 = [
        UnidadeDocumento(
            id_unidade=f"{id_doc}-p2-u1",
            id_documento=id_doc,
            id_pagina=f"{id_doc}-p2",
            tipo="formula",
            texto=" softmax(z_i) = exp(z_i) / soma(exp(z_j)) ",
            ordem_leitura=1,
            caixa=CaixaDelimitadora(20.0, 50.0, 250.0, 90.0),
            fonte="native",
        ),
        UnidadeDocumento(
            id_unidade=f"{id_doc}-p2-u2",
            id_documento=id_doc,
            id_pagina=f"{id_doc}-p2",
            tipo="paragraph",
            texto="Camada densa final e classificação multiclasse com entropia cruzada.",
            ordem_leitura=2,
            caixa=CaixaDelimitadora(20.0, 100.0, 350.0, 180.0),
            fonte="native",
        ),
    ]
    # Página 3 propositalmente sem unidades finas para testar fallback de alinhamento por página
    texto_p1 = (
        "Redes Neurais Convolucionais e Filtros Espaciais "
        "Diagrama da convolução 2D com stride e padding sobre matriz de pixels"
    )
    texto_p2 = (
        "softmax(z_i) = exp(z_i) / soma(exp(z_j)) "
        "Camada densa final e classificação multiclasse com entropia cruzada."
    )
    texto_p3 = (
        "Regularização Dropout e Normalização em Lote Batch Normalization "
        "para evitar sobreajuste durante o treinamento profundo."
    )

    paginas = [
        PaginaDocumento(
            id_pagina=f"{id_doc}-p1",
            numero_pagina=1,
            texto_nativo=texto_p1,
            texto_normalizado=texto_p1,
            metodo_extracao="mixed",
            unidades=unidades_p1,
        ),
        PaginaDocumento(
            id_pagina=f"{id_doc}-p2",
            numero_pagina=2,
            texto_nativo=texto_p2,
            texto_normalizado=texto_p2,
            metodo_extracao="native",
            unidades=unidades_p2,
        ),
        PaginaDocumento(
            id_pagina=f"{id_doc}-p3",
            numero_pagina=3,
            texto_nativo=texto_p3,
            texto_normalizado=texto_p3,
            metodo_extracao="native",
            unidades=[],
        ),
    ]

    return Documento(
        id_documento=id_doc,
        uri_origem=f"/dados/{id_doc}.pdf",
        titulo="Aula de CNN e Regularização",
        paginas=paginas,
        versao_processamento="1.0",
        proveniencia=ProvenienciaDocumento(
            uri_origem=f"/dados/{id_doc}.pdf",
            metodo_extracao="mixed",
            versao_pipeline="1.0",
        ),
    )


def _criar_aula_fase6(id_aula: str = "aula-f6") -> Aula:
    textos = [
        (
            "Vamos iniciar pelas redes neurais convolucionais e pelo diagrama "
            "da convolução 2D com stride e padding.",
            "explanation",
        ),
        (
            "Em seguida passamos para a camada densa com softmax e entropia cruzada.",
            "explanation",
        ),
        (
            "Por fim aplicamos regularização dropout e batch normalization no treinamento.",
            "explanation",
        ),
        (
            "Voltando ao primeiro slide, observem novamente os filtros espaciais "
            "da convolução 2D na matriz de pixels.",
            "reference",
        ),
        (
            "Aviso administrativo: a secretaria estará fechada no feriado municipal.",
            "contextualization",
        ),
    ]
    segmentos = []
    intervalos = []
    for idx, (txt, tipo) in enumerate(textos, start=1):
        t0 = float((idx - 1) * 10)
        t1 = t0 + 8.0
        seg = SegmentoTranscricao(
            id_segmento=f"seg-{id_aula}-{idx}",
            id_aula=id_aula,
            texto=txt,
            intervalo=IntervaloTempo(t0, t1),
            ordem=idx,
        )
        inter = IntervaloExplicativo(
            id_intervalo=f"inter-{id_aula}-{idx}",
            id_aula=id_aula,
            texto=txt,
            intervalo=IntervaloTempo(t0, t1),
            ordem=idx,
            ids_segmentos=[seg.id_segmento],
            tipo=tipo,
        )
        segmentos.append(seg)
        intervalos.append(inter)

    return Aula(
        id_aula=id_aula,
        titulo="Aula CNN Completa",
        uri_origem=f"/dados/{id_aula}.wav",
        caminho_arquivo=Path(f"/dados/{id_aula}.wav"),
        metadados=MetadadosAudio(duracao=55.0, taxa_amostragem=16000, canais=1, formato="wav"),
        segmentos=segmentos,
        intervalos=intervalos,
        idioma="pt",
    )


def _resultado_recuperacao_sintetico(
    ordem: int,
    scores_paginas: dict[tuple[str, int], float],
    unidades_por_pag: dict[str, tuple[CandidatoUnidade, ...]] | None = None,
) -> ResultadoRecuperacaoIntervalo:
    unidades_por_pag = unidades_por_pag or {}
    cands_p = []
    for (id_p, num_p), sc in sorted(
        scores_paginas.items(), key=lambda x: x[1], reverse=True
    ):
        if sc > 0.0:
            cands_p.append(
                CandidatoPagina(
                    id_pagina=id_p,
                    numero_pagina=num_p,
                    texto=f"Texto {id_p}",
                    pontuacao=sc,
                    pontuacao_direta=sc,
                    pontuacao_unidades=0.0,
                    estrategia="bm25",
                    unidades_evidencia=unidades_por_pag.get(id_p, ()),
                )
            )
    maior = cands_p[0].pontuacao if cands_p else 0.0
    return ResultadoRecuperacaoIntervalo(
        id_intervalo=f"inter-{ordem}",
        ordem_intervalo=ordem,
        texto_intervalo=f"Intervalo {ordem}",
        intervalo_tempo=IntervaloTempo(float((ordem - 1) * 10), float(ordem * 10 - 2)),
        id_documento="doc-sintetico",
        estrategia="bm25",
        candidatos_pagina=tuple(cands_p),
        candidatos_unidade=(),
        abstido=maior <= 0.0,
        limiar_abstencao=0.0,
        maior_pontuacao=maior,
    )


# --- 1. Testes de Funções Puras de Domínio (Kernel e HMM) ---


def test_contexto_temporal_kernel_desambigua_e_permite_retorno() -> None:
    mapa_num = {"p1": 1, "p2": 2, "p5": 5}
    # Intervalo 0 em p1, Intervalo 1 ambíguo (p1=0.50 vs p5=0.52), Intervalo 2 em p1
    r0 = _resultado_recuperacao_sintetico(1, {("p1", 1): 0.90})
    r1 = _resultado_recuperacao_sintetico(2, {("p5", 5): 0.52, ("p1", 1): 0.50})
    r2 = _resultado_recuperacao_sintetico(3, {("p1", 1): 0.85})
    base = [r0, r1, r2]

    suporte_p1 = calcular_contexto_temporal_pagina(1, base, "p1", mapa_num, janela=2)
    suporte_p5 = calcular_contexto_temporal_pagina(1, base, "p5", mapa_num, janela=2)

    assert suporte_p1 > 0.80
    assert suporte_p5 == 0.0

    pesos = PesosAlinhamento(peso_similaridade=0.75, peso_temporal=0.20, peso_visual=0.05)
    score_final_p1 = combinar_sinais_alinhamento(0.50, suporte_p1, 0.0, pesos)
    score_final_p5 = combinar_sinais_alinhamento(0.52, suporte_p5, 0.0, pesos)

    # Contexto temporal de vizinhança desambigua a favor de p1 sem penalizar p5
    assert score_final_p1 > score_final_p5
    assert score_final_p5 == 0.52


def test_evidencia_visual_pagina() -> None:
    u_texto = CandidatoUnidade(
        id_unidade="u1",
        id_pagina="p1",
        numero_pagina=1,
        tipo_unidade="paragraph",
        ordem_leitura=1,
        texto="Parágrafo comum",
        pontuacao=0.9,
        estrategia="bm25",
        fonte="native",
    )
    u_figura = CandidatoUnidade(
        id_unidade="u2",
        id_pagina="p1",
        numero_pagina=1,
        tipo_unidade="figure",
        ordem_leitura=2,
        texto="Figura OCR",
        pontuacao=0.75,
        estrategia="bm25",
        fonte="ollama",
    )
    cp = CandidatoPagina(
        id_pagina="p1",
        numero_pagina=1,
        texto="Texto",
        pontuacao=0.8,
        pontuacao_direta=0.8,
        pontuacao_unidades=0.8,
        estrategia="bm25",
        unidades_evidencia=(u_texto, u_figura),
    )
    assert calcular_evidencia_visual_pagina(cp) == 0.75

    u_google = CandidatoUnidade(
        id_unidade="u3",
        id_pagina="p1",
        numero_pagina=1,
        tipo_unidade="block",
        ordem_leitura=3,
        texto="Conteúdo Google AI Studio",
        pontuacao=0.82,
        estrategia="bm25",
        fonte="google_ai_studio",
    )
    cp_google = CandidatoPagina(
        id_pagina="p1",
        numero_pagina=1,
        texto="Texto",
        pontuacao=0.8,
        pontuacao_direta=0.8,
        pontuacao_unidades=0.8,
        estrategia="bm25",
        unidades_evidencia=(u_texto, u_google),
    )
    assert calcular_evidencia_visual_pagina(cp_google) == 0.82


def test_hmm_forward_backward_estocasticidade_e_suavizacao() -> None:
    paginas_ordenadas = [("p1", 1), ("p2", 2), ("p3", 3)]
    # Intervalo 1 forte em p1, Intervalo 2 ambíguo entre p1 e p3, Intervalo 3 forte em p1
    r1 = _resultado_recuperacao_sintetico(1, {("p1", 1): 0.90})
    r2 = _resultado_recuperacao_sintetico(2, {("p1", 1): 0.50, ("p3", 3): 0.51})
    r3 = _resultado_recuperacao_sintetico(3, {("p1", 1): 0.90})

    posteriores = calcular_posteriores_hmm(
        resultados_base=[r1, r2, r3],
        paginas_ordenadas=paginas_ordenadas,
        params_hmm=ParametrosHMM(temperatura_emissao=0.15),
    )

    assert len(posteriores) == 3
    for gamma_pags, gamma_abs in posteriores:
        soma_total = sum(gamma_pags.values()) + gamma_abs
        assert math.isclose(soma_total, 1.0, abs_tol=1e-2)

    # No intervalo intermediário (índice 1), o forward-backward favorece p1 por continuidade
    gamma_meio, abs_meio = posteriores[1]
    assert gamma_meio["p1"] > gamma_meio["p3"]
    assert gamma_meio["p1"] > abs_meio


def test_hmm_permite_salto_nao_sequencial_e_abstencao() -> None:
    paginas_ordenadas = [("p1", 1), ("p2", 2), ("p3", 3)]
    # Sequência: p3 -> retorno forte para p1 -> sem evidência (abstenção)
    r1 = _resultado_recuperacao_sintetico(1, {("p3", 3): 0.92})
    r2 = _resultado_recuperacao_sintetico(2, {("p1", 1): 0.95})
    r3 = _resultado_recuperacao_sintetico(3, {})

    posteriores = calcular_posteriores_hmm(
        resultados_base=[r1, r2, r3],
        paginas_ordenadas=paginas_ordenadas,
        params_hmm=ParametrosHMM(temperatura_emissao=0.10),
    )

    # Intervalo 1 em p3
    assert posteriores[0][0]["p3"] > posteriores[0][0]["p1"]
    # Intervalo 2 salta de p3 de volta para p1 graças à emissão forte sem monotonicidade rígida
    assert posteriores[1][0]["p1"] > posteriores[1][0]["p3"]
    assert posteriores[1][0]["p1"] > posteriores[1][1]
    # Intervalo 3 sem evidência tem estado de abstenção dominante
    gamma_pags_3, gamma_abs_3 = posteriores[2]
    assert gamma_abs_3 > max(gamma_pags_3.values())


# --- 2. Testes do Caso de Uso AlinharAula (Baselines, Kernel, HMM, Hierarquia e Manual) ---


def test_alinhar_aula_estrategias_kernel_e_hierarquica(tmp_path: Path) -> None:
    banco = tmp_path / "anotai.sqlite"
    repo_doc = RepositorioDocumentoSQLite(banco)
    repo_aula = RepositorioAulaSQLite(banco)
    repo_alin = RepositorioAlinhamentoSQLite(banco)

    doc = _criar_documento_fase6("doc-1")
    aula = _criar_aula_fase6("aula-1")
    repo_doc.salvar(doc)
    repo_aula.salvar(aula)

    recuperador = RecuperarCandidatos(
        indice_paginas=IndiceBM25(),
        indice_unidades=IndiceBM25(),
        estrategia="bm25",
    )

    alinhador = AlinharAula(
        recuperador=recuperador,
        repositorio_alinhamento=repo_alin,
        estrategia="hierarchical",
        modelo_temporal="kernel",
        limiar_abstencao=0.05,
    )

    resultados = alinhador.executar(aula, doc)
    assert len(resultados) == 5

    # Intervalo 1 -> Pág. 1 e unidades da Pág. 1 (incluindo figura OCR com evidência)
    r1 = resultados[0].alinhamento
    assert r1.status == StatusAlinhamento.ALINHADO.value
    assert "doc-1-p1" in r1.ids_paginas
    assert len(r1.ids_unidades) >= 1
    assert all(u.startswith("doc-1-p1-") for u in r1.ids_unidades)
    assert "ev-ocr-p1-u2" in r1.ids_evidencias or "ev-nativa-p1-u1" in r1.ids_evidencias

    # Intervalo 2 -> Pág. 2
    r2 = resultados[1].alinhamento
    assert r2.status == StatusAlinhamento.ALINHADO.value
    assert "doc-1-p2" in r2.ids_paginas

    # Intervalo 3 -> Pág. 3 (sem unidades finas -> alinha por página com ids_unidades=[])
    r3 = resultados[2].alinhamento
    assert r3.status == StatusAlinhamento.ALINHADO.value
    assert r3.ids_paginas == ["doc-1-p3"]
    assert r3.ids_unidades == []

    # Intervalo 4 -> Retorno não sequencial à Pág. 1 com tipo_relacao='reference'
    r4 = resultados[3].alinhamento
    assert r4.status == StatusAlinhamento.ALINHADO.value
    assert "doc-1-p1" in r4.ids_paginas
    assert r4.tipo_relacao == "reference"

    # Intervalo 5 -> Aviso administrativo sem evidência -> Abstenção
    r5 = resultados[4].alinhamento
    assert r5.status == StatusAlinhamento.ABSTIDO.value
    assert r5.ids_paginas == []
    assert r5.ids_unidades == []
    assert r5.tipo_relacao is None

    # Verifica persistência no SQLite
    salvos = repo_alin.listar_por_aula(aula.id_aula, doc.id_documento, estrategia="hierarchical")
    assert len(salvos) == 5


def test_alinhar_aula_hmm_nao_duplica_similaridade_e_persiste_estrategia(tmp_path: Path) -> None:
    banco = tmp_path / "anotai.sqlite"
    repo_doc = RepositorioDocumentoSQLite(banco)
    repo_aula = RepositorioAulaSQLite(banco)
    repo_alin = RepositorioAlinhamentoSQLite(banco)

    doc = _criar_documento_fase6("doc-1")
    aula = _criar_aula_fase6("aula-1")
    repo_doc.salvar(doc)
    repo_aula.salvar(aula)

    recuperador = RecuperarCandidatos(
        indice_paginas=IndiceBM25(),
        indice_unidades=IndiceBM25(),
        estrategia="bm25",
    )

    alinhador_hmm = AlinharAula(
        recuperador=recuperador,
        repositorio_alinhamento=repo_alin,
        estrategia="hierarchical",
        modelo_temporal="hmm",
        parametros_hmm=ParametrosHMM(temperatura_emissao=0.12),
    )

    assert alinhador_hmm.estrategia == "hierarchical_hmm"
    resultados = alinhador_hmm.executar(aula, doc)
    assert len(resultados) == 5

    # Verifica que pontuacao_final das páginas em *_hmm é exatamente pontuacao_temporal (gamma)
    for res in resultados:
        assert res.probabilidade_abstencao_hmm is not None
        for cp in res.candidatos_pagina:
            assert cp.pontuacao_final == cp.pontuacao_temporal

    # Intervalo 5 deve abster-se no HMM
    assert resultados[4].alinhamento.status == StatusAlinhamento.ABSTIDO.value

    salvos_hmm = repo_alin.listar_por_aula(
        aula.id_aula, doc.id_documento, estrategia="hierarchical_hmm"
    )
    assert len(salvos_hmm) == 5


def test_revisao_manual_coexiste_com_alinhamento_automatico(tmp_path: Path) -> None:
    banco = tmp_path / "anotai.sqlite"
    repo_doc = RepositorioDocumentoSQLite(banco)
    repo_aula = RepositorioAulaSQLite(banco)
    repo_alin = RepositorioAlinhamentoSQLite(banco)

    doc = _criar_documento_fase6("doc-1")
    aula = _criar_aula_fase6("aula-1")
    repo_doc.salvar(doc)
    repo_aula.salvar(aula)

    recuperador = RecuperarCandidatos(IndiceBM25(), IndiceBM25())
    alinhador = AlinharAula(
        recuperador=recuperador,
        repositorio_alinhamento=repo_alin,
        estrategia="bm25",
    )
    alinhador.executar(aula, doc)

    # Registra revisão manual no intervalo 1 informando apenas a unidade (infere a página-mãe)
    alin_manual = alinhador.registrar_revisao_manual(
        aula=aula,
        documento=doc,
        id_intervalo="inter-aula-1-1",
        ids_unidades=["doc-1-p2-u1"],
        justificativa="Correção manual pelo docente",
    )

    assert alin_manual.origem == OrigemAlinhamento.MANUAL.value
    assert alin_manual.estrategia == "manual"
    assert alin_manual.ids_paginas == ["doc-1-p2"]
    assert alin_manual.ids_unidades == ["doc-1-p2-u1"]

    por_intervalo = repo_alin.listar_por_intervalo("inter-aula-1-1")
    origens = {a.origem for a in por_intervalo}
    assert origens == {"automatic", "manual"}


# --- 3. Testes de Formatação e CLI (Subcomando alinhar) ---


def test_cli_comando_alinhar_kernel_hmm_e_manual(capsys) -> None:
    doc = _criar_documento_fase6("doc-1")
    aula = _criar_aula_fase6("aula-1")

    mock_repo_aula = MagicMock()
    mock_repo_aula.buscar_por_id.return_value = aula
    mock_repo_doc = MagicMock()
    mock_repo_doc.buscar_por_id.return_value = doc
    mock_repo_alin = MagicMock()

    settings = Settings(database_path="dummy.sqlite", abstention_threshold=0.0)

    # 1. Execução com HMM em formato texto
    args = MagicMock(
        id_aula="aula-1",
        id_documento="doc-1",
        strategy="hierarchical",
        base_strategy="bm25",
        temporal_model="hmm",
        threshold=0.0,
        temporal_weight=None,
        visual_weight=None,
        window=None,
        hmm_temperature=0.12,
        max_paginas=3,
        max_unidades=5,
        intervalo=1,
        manual=False,
        paginas=None,
        unidades=None,
        abster=False,
        justificativa=None,
        format="text",
        model=None,
    )

    cod = executar_comando_alinhar(
        args,
        settings,
        repo_aula_cls=lambda _: mock_repo_aula,
        repo_doc_cls=lambda _: mock_repo_doc,
        repo_alin_cls=lambda _: mock_repo_alin,
    )
    assert cod == 0
    saida = capsys.readouterr().out
    assert "AnotaAI — Alinhamento Temporal e Hierárquico" in saida
    assert "HIERARCHICAL_HMM" in saida
    assert mock_repo_alin.salvar_lote.called

    # 2. Execução de revisão manual em JSON
    args.manual = True
    args.paginas = "doc-1-p1"
    args.unidades = "doc-1-p1-u1"
    args.format = "json"
    cod_man = executar_comando_alinhar(
        args,
        settings,
        repo_aula_cls=lambda _: mock_repo_aula,
        repo_doc_cls=lambda _: mock_repo_doc,
        repo_alin_cls=lambda _: mock_repo_alin,
    )
    assert cod_man == 0
    saida_json = capsys.readouterr().out
    assert '"origem": "manual"' in saida_json
    assert mock_repo_alin.salvar.called


def test_cli_alinhar_via_main_help(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["alinhar", "--help"])
    assert exc_info.value.code == 0
    capturado = capsys.readouterr().out
    assert "--temporal-model" in capturado
    assert "--strategy" in capturado
    assert "--manual" in capturado
