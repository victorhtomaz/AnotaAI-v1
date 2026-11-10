from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anotai.adapters.inbound.cli.comando_buscar import executar_comando_buscar
from anotai.adapters.inbound.cli.formatador_terminal import formatar_recuperacao_texto
from anotai.adapters.inbound.cli.principal import main
from anotai.adapters.outbound.ollama.provedor_embedding import ProvedorEmbeddingOllama
from anotai.adapters.outbound.search import IndiceBM25, IndiceEmbeddings, IndiceHibrido
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
from anotai.domain.exceptions import ErroBusca
from anotai.domain.value_objects import (
    CaixaDelimitadora,
    CandidatoPagina,
    CandidatoUnidade,
    IntervaloTempo,
    MetadadosAudio,
    ProvenienciaDocumento,
    ResultadoRecuperacaoIntervalo,
    agregar_pontuacao_unidades,
    combinar_pontuacao_pagina,
)


def _criar_documento_teste(id_doc: str = "doc-teste") -> Documento:
    unidades_p1 = [
        UnidadeDocumento(
            id_unidade=f"{id_doc}-p1-u1",
            id_documento=id_doc,
            id_pagina=f"{id_doc}-p1",
            tipo="title",
            texto="Introdução aos Modelos de Aprendizado Supervisionado",
            ordem_leitura=1,
            caixa=CaixaDelimitadora(10.0, 10.0, 200.0, 30.0),
            fonte="native",
        ),
        UnidadeDocumento(
            id_unidade=f"{id_doc}-p1-u2",
            id_documento=id_doc,
            id_pagina=f"{id_doc}-p1",
            tipo="paragraph",
            texto="Classificação e regressão linear são abordagens fundamentais.",
            ordem_leitura=2,
            caixa=CaixaDelimitadora(10.0, 40.0, 300.0, 100.0),
            fonte="native",
        ),
        UnidadeDocumento(
            id_unidade=f"{id_doc}-p1-u-decorativa",
            id_documento=id_doc,
            id_pagina=f"{id_doc}-p1",
            tipo="figure",
            texto="Logotipo da universidade no cabeçalho",
            ordem_leitura=3,
            caixa=CaixaDelimitadora(500.0, 10.0, 550.0, 60.0),
            fonte="native",
            eh_decorativa=True,
        ),
    ]

    unidades_p2 = [
        UnidadeDocumento(
            id_unidade=f"{id_doc}-p2-u1",
            id_documento=id_doc,
            id_pagina=f"{id_doc}-p2",
            tipo="formula",
            texto="y = Wx + b",
            ordem_leitura=1,
            caixa=CaixaDelimitadora(50.0, 100.0, 150.0, 130.0),
            fonte="native",
        ),
        UnidadeDocumento(
            id_unidade=f"{id_doc}-p2-u2",
            id_documento=id_doc,
            id_pagina=f"{id_doc}-p2",
            tipo="paragraph",
            texto="Função de perda do erro quadrático médio para otimização dos pesos.",
            ordem_leitura=2,
            caixa=CaixaDelimitadora(50.0, 140.0, 350.0, 200.0),
            fonte="native",
        ),
    ]

    texto_p1 = (
        "Introdução aos Modelos de Aprendizado Supervisionado "
        "Classificação e regressão linear"
    )
    texto_p2 = (
        "y = Wx + b Função de perda do erro quadrático médio para otimização dos pesos."
    )

    paginas = [
        PaginaDocumento(
            id_pagina=f"{id_doc}-p1",
            numero_pagina=1,
            texto_nativo=texto_p1,
            texto_normalizado=texto_p1,
            metodo_extracao="native",
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
    ]

    return Documento(
        id_documento=id_doc,
        uri_origem=f"/dados/{id_doc}.pdf",
        titulo="Slides de Machine Learning",
        paginas=paginas,
        versao_processamento="v1",
        proveniencia=ProvenienciaDocumento(
            uri_origem=f"/dados/{id_doc}.pdf",
            metodo_extracao="native",
            versao_pipeline="v1",
        ),
    )


def _criar_aula_teste(id_aula: str = "aula-teste") -> Aula:
    seg1 = SegmentoTranscricao(
        id_segmento=f"seg-{id_aula}-1",
        id_aula=id_aula,
        texto="Hoje começamos o módulo de aprendizado supervisionado com modelos lineares.",
        intervalo=IntervaloTempo(0.0, 6.0),
        ordem=1,
    )
    seg2 = SegmentoTranscricao(
        id_segmento=f"seg-{id_aula}-2",
        id_aula=id_aula,
        texto="Aqui temos a equação y = Wx + b com a função de perda do erro quadrático.",
        intervalo=IntervaloTempo(6.5, 14.0),
        ordem=2,
    )
    seg3 = SegmentoTranscricao(
        id_segmento=f"seg-{id_aula}-3",
        id_aula=id_aula,
        texto="Lembrando a todos que o prazo de entrega do trabalho é sexta-feira às 23 horas.",
        intervalo=IntervaloTempo(15.0, 22.0),
        ordem=3,
    )

    inter1 = IntervaloExplicativo(
        id_intervalo=f"inter-{id_aula}-1",
        id_aula=id_aula,
        texto=seg1.texto,
        intervalo=seg1.intervalo,
        ordem=1,
        ids_segmentos=[seg1.id_segmento],
    )
    inter2 = IntervaloExplicativo(
        id_intervalo=f"inter-{id_aula}-2",
        id_aula=id_aula,
        texto=seg2.texto,
        intervalo=seg2.intervalo,
        ordem=2,
        ids_segmentos=[seg2.id_segmento],
    )
    inter3 = IntervaloExplicativo(
        id_intervalo=f"inter-{id_aula}-3",
        id_aula=id_aula,
        texto=seg3.texto,
        intervalo=seg3.intervalo,
        ordem=3,
        ids_segmentos=[seg3.id_segmento],
    )

    return Aula(
        id_aula=id_aula,
        titulo="Aula 01 - Aprendizado Supervisionado",
        uri_origem=f"/dados/{id_aula}.wav",
        caminho_arquivo=Path(f"/dados/{id_aula}.wav"),
        metadados=MetadadosAudio(duracao=25.0, taxa_amostragem=16000, canais=1, formato="wav"),
        segmentos=[seg1, seg2, seg3],
        intervalos=[inter1, inter2, inter3],
        idioma="pt",
    )


# --- 1. Testes de Funções de Pontuação e Agregação ---


def test_agregar_pontuacao_unidades() -> None:
    # Caso vazio ou sem positivos
    assert agregar_pontuacao_unidades([]) == 0.0
    assert agregar_pontuacao_unidades([0.0, -0.2]) == 0.0

    # 1 unidade
    assert agregar_pontuacao_unidades([0.8]) == 0.8

    # 2 unidades: u1 + 0.25 * u2
    assert agregar_pontuacao_unidades([0.8, 0.4]) == round(0.8 + 0.25 * 0.4, 4)

    # 3 unidades: u1 + 0.25 * u2 + 0.15 * u3
    esperado = round(0.8 + 0.25 * 0.4 + 0.15 * 0.2, 4)
    assert agregar_pontuacao_unidades([0.2, 0.8, 0.4]) == esperado

    # Saturação máxima em 1.0
    assert agregar_pontuacao_unidades([0.9, 0.8, 0.7]) == 1.0


def test_combinar_pontuacao_pagina() -> None:
    # Apenas direto
    assert combinar_pontuacao_pagina(0.7, 0.0) == 0.7
    # Apenas unidades
    assert combinar_pontuacao_pagina(0.0, 0.6) == 0.6
    # Ambos presentes -> média balanceada
    assert combinar_pontuacao_pagina(0.8, 0.6) == 0.7


# --- 2. Testes de Índice BM25 ---


def test_indice_bm25_recuperacao() -> None:
    indice = IndiceBM25()
    itens = [
        ("p1", "Introdução ao aprendizado supervisionado e classificação"),
        ("p2", "Equação do modelo linear y = Wx + b com erro quadrático"),
    ]
    indice.indexar(itens)

    consultas = [
        "aprendizado supervisionado",
        "equação linear erro quadrático",
        "conteúdo totalmente inexistente abracadabra xyz",
    ]
    resultados = indice.consultar_lote(consultas, top_k=2)

    assert len(resultados) == 3

    # Consulta 1 deve ranquear p1 em primeiro
    assert len(resultados[0]) >= 1
    assert resultados[0][0][0] == "p1"
    assert 0.0 < resultados[0][0][1] <= 1.0

    # Consulta 2 deve ranquear p2 em primeiro
    assert len(resultados[1]) >= 1
    assert resultados[1][0][0] == "p2"
    assert 0.0 < resultados[1][0][1] <= 1.0

    # Consulta 3 sem correspondência
    assert resultados[2] == []


def test_indice_bm25_casos_limites() -> None:
    indice = IndiceBM25()
    # Sem indexar nada
    assert indice.consultar_lote(["teste"]) == [[]]

    # Lista vazia de consultas
    assert indice.consultar_lote([]) == []

    # Corpus vazio
    indice.indexar([])
    assert indice.consultar_lote(["teste"]) == [[]]


# --- 3. Testes de ProvedorEmbedding e IndiceEmbeddings ---


class ClienteOllamaFake:
    def __init__(self, falhar: bool = False) -> None:
        self.falhar = falhar

    def embed(self, model: str, input: list[str], **kwargs):
        if self.falhar:
            raise RuntimeError("Ollama indisponível")
        # Simula geração determinística de embedding baseada em palavras-chave simples
        vetores = []
        for texto in input:
            t = texto.lower()
            # Vetor em 3D: [aprendizado/supervisionado, linear/equacao/quadratico, entrega/trabalho]
            tem_aprendizado = any(
                k in t for k in ("aprendizado", "supervisionado", "classificação")
            )
            tem_linear = any(
                k in t for k in ("linear", "equação", "quadrático", "wx", "perda")
            )
            tem_entrega = any(k in t for k in ("entrega", "trabalho", "sexta"))
            v = [
                1.0 if tem_aprendizado else 0.0,
                1.0 if tem_linear else 0.0,
                1.0 if tem_entrega else 0.0,
            ]
            # Se for tudo zero, adiciona ruído mínimo para não ter vetor nulo
            if sum(v) == 0.0:
                v = [0.01, 0.01, 0.01]
            vetores.append(v)
        return {"embeddings": vetores}


def test_provedor_embedding_ollama() -> None:
    cliente = ClienteOllamaFake()
    provedor = ProvedorEmbeddingOllama(cliente=cliente, modelo="bge-m3:567m")

    vetores = provedor.gerar_embeddings(["Texto um", "Texto dois"])
    assert len(vetores) == 2
    assert len(vetores[0]) == 3

    # Teste de cache: quando o cliente passa a falhar, textos já em cache continuam retornando
    cliente.falhar = True
    vetores_cacheados = provedor.gerar_embeddings(["Texto um"])
    assert vetores_cacheados == [vetores[0]]

    # Novo texto não cacheado deve disparar erro
    with pytest.raises(ErroBusca, match="Falha ao gerar embeddings"):
        provedor.gerar_embeddings(["Novo texto sem cache"])

    assert provedor.gerar_embeddings([]) == []

    cliente_erro = ClienteOllamaFake(falhar=True)
    provedor_erro = ProvedorEmbeddingOllama(cliente=cliente_erro)
    with pytest.raises(ErroBusca, match="Falha ao gerar embeddings"):
        provedor_erro.gerar_embeddings(["teste"])


def test_indice_embeddings_recuperacao() -> None:
    provedor = ProvedorEmbeddingOllama(cliente=ClienteOllamaFake())
    indice = IndiceEmbeddings(provedor=provedor)

    itens = [
        ("doc1", "Classificação em aprendizado supervisionado"),
        ("doc2", "Otimização de pesos da equação linear"),
    ]
    indice.indexar(itens)

    consultas = [
        "modelos de aprendizado supervisionado",
        "otimização da equação linear",
    ]
    resultados = indice.consultar_lote(consultas, top_k=2)

    assert len(resultados) == 2
    assert resultados[0][0][0] == "doc1"
    assert resultados[1][0][0] == "doc2"
    assert 0.0 < resultados[0][0][1] <= 1.0


# --- 4. Testes de IndiceHibrido ---


def test_indice_hibrido_fusao() -> None:
    idx_lex = IndiceBM25()
    provedor = ProvedorEmbeddingOllama(cliente=ClienteOllamaFake())
    idx_sem = IndiceEmbeddings(provedor=provedor)

    idx_hibrido = IndiceHibrido(
        indice_lexico=idx_lex,
        indice_semantico=idx_sem,
        peso_semantica=0.5,
    )

    itens = [
        ("item1", "Introdução ao aprendizado supervisionado"),
        ("item2", "Cálculo da função de perda da regressão linear"),
    ]
    idx_hibrido.indexar(itens)

    consultas = ["aprendizado supervisionado", "regressão linear"]
    resultados = idx_hibrido.consultar_lote(consultas, top_k=2)

    assert len(resultados) == 2
    assert resultados[0][0][0] == "item1"
    assert resultados[1][0][0] == "item2"


# --- 5. Testes de Caso de Uso: RecuperarCandidatos ---


def test_recuperar_candidatos_caso_de_uso_completo() -> None:
    doc = _criar_documento_teste("doc-1")
    aula = _criar_aula_teste("aula-1")

    idx_pag = IndiceBM25()
    idx_uni = IndiceBM25()

    recuperador = RecuperarCandidatos(
        indice_paginas=idx_pag,
        indice_unidades=idx_uni,
        estrategia="bm25",
        top_k_paginas=5,
        top_k_unidades=5,
        limiar_abstencao=0.0,
    )

    resultados = recuperador.executar(aula, doc)
    assert len(resultados) == 3

    # Intervalo 1: Aprendizado supervisionado -> P1 e unidades da P1
    res1 = resultados[0]
    assert res1.id_intervalo == "inter-aula-1-1"
    assert not res1.abstido
    assert len(res1.candidatos_pagina) >= 1
    assert res1.candidatos_pagina[0].numero_pagina == 1

    # Garante que unidades decorativas NUNCA entram como candidatos
    todos_ids_unidades = [u.id_unidade for r in resultados for u in r.candidatos_unidade]
    assert "doc-1-p1-u-decorativa" not in todos_ids_unidades

    # Intervalo 2: Equação linear y = Wx + b -> P2 e unidades da P2
    res2 = resultados[1]
    assert not res2.abstido
    assert res2.candidatos_pagina[0].numero_pagina == 2

    # Intervalo 3: Aviso de trabalho/prazo -> sem correspondência documental
    res3 = resultados[2]
    assert res3.abstido
    assert "Nenhuma evidência documental" in (res3.motivo_abstencao or "")


def test_recuperar_candidatos_abstenção_por_limiar() -> None:
    doc = _criar_documento_teste("doc-1")
    aula = _criar_aula_teste("aula-1")

    idx_pag = IndiceBM25()
    idx_uni = IndiceBM25()

    # Com limiar de abstenção muito alto (0.95), intervalos que teriam score 0.3-0.5 são abstidos
    recuperador = RecuperarCandidatos(
        indice_paginas=idx_pag,
        indice_unidades=idx_uni,
        estrategia="bm25",
        limiar_abstencao=0.95,
    )

    resultados = recuperador.executar(aula, doc)
    assert all(r.abstido for r in resultados)
    assert "abaixo do limiar de abstenção" in (resultados[0].motivo_abstencao or "")


# --- 6. Testes de Formatação e CLI ---


def test_formatador_recuperacao_texto() -> None:
    doc = _criar_documento_teste("doc-1")
    aula = _criar_aula_teste("aula-1")

    cand_u = CandidatoUnidade(
        id_unidade="doc-1-p1-u1",
        id_pagina="doc-1-p1",
        numero_pagina=1,
        tipo_unidade="title",
        ordem_leitura=1,
        texto="Introdução aos Modelos",
        pontuacao=0.85,
        estrategia="bm25",
        fonte="native",
    )
    cand_p = CandidatoPagina(
        id_pagina="doc-1-p1",
        numero_pagina=1,
        texto="Texto da página 1",
        pontuacao=0.88,
        pontuacao_direta=0.85,
        pontuacao_unidades=0.91,
        estrategia="bm25",
        unidades_evidencia=(cand_u,),
    )
    res_alinhado = ResultadoRecuperacaoIntervalo(
        id_intervalo="inter-1",
        ordem_intervalo=1,
        texto_intervalo="Fala sobre o tema.",
        intervalo_tempo=IntervaloTempo(0.0, 5.0),
        id_documento="doc-1",
        estrategia="bm25",
        candidatos_pagina=(cand_p,),
        candidatos_unidade=(cand_u,),
        abstido=False,
        limiar_abstencao=0.0,
        maior_pontuacao=0.88,
    )
    res_abstido = ResultadoRecuperacaoIntervalo(
        id_intervalo="inter-2",
        ordem_intervalo=2,
        texto_intervalo="Aviso genérico.",
        intervalo_tempo=IntervaloTempo(6.0, 10.0),
        id_documento="doc-1",
        estrategia="bm25",
        candidatos_pagina=(),
        candidatos_unidade=(),
        abstido=True,
        limiar_abstencao=0.0,
        maior_pontuacao=0.0,
        motivo_abstencao="Sem evidências",
    )

    saida = formatar_recuperacao_texto(aula, doc, [res_alinhado, res_abstido])

    assert "AnotaAI — Recuperação e Busca de Candidatos" in saida
    assert "não probabilidade calibrada" in saida
    assert "Pág. 01 (score: 0.8800" in saida
    assert "[ABSTENÇÃO] Sem evidências" in saida


def test_cli_comando_buscar(capsys) -> None:
    doc = _criar_documento_teste("doc-1")
    aula = _criar_aula_teste("aula-1")

    mock_repo_aula = MagicMock()
    mock_repo_aula.buscar_por_id.return_value = aula
    mock_repo_doc = MagicMock()
    mock_repo_doc.buscar_por_id.return_value = doc

    settings = Settings(database_path="dummy.sqlite", abstention_threshold=0.0)

    # Chamada com formato text
    args = MagicMock(
        id_aula="aula-1",
        id_documento="doc-1",
        strategy="bm25",
        top_k_paginas=3,
        top_k_unidades=3,
        threshold=0.0,
        intervalo=1,
        format="text",
        model=None,
    )

    cod = executar_comando_buscar(
        args,
        settings,
        repo_aula_cls=lambda _: mock_repo_aula,
        repo_doc_cls=lambda _: mock_repo_doc,
    )
    assert cod == 0
    saida = capsys.readouterr().out
    assert "AnotaAI — Recuperação e Busca de Candidatos" in saida
    assert "[01]" in saida

    # Chamada com formato json
    args.format = "json"
    args.intervalo = None
    cod_json = executar_comando_buscar(
        args,
        settings,
        repo_aula_cls=lambda _: mock_repo_aula,
        repo_doc_cls=lambda _: mock_repo_doc,
    )
    assert cod_json == 0
    saida_json = capsys.readouterr().out
    assert '"id_intervalo": "inter-aula-1-1"' in saida_json


def test_cli_buscar_via_main_help(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["buscar", "--help"])
    assert exc_info.value.code == 0
    capturado = capsys.readouterr().out
    assert "--strategy" in capturado
    assert "--top-k-paginas" in capturado
    assert "--threshold" in capturado
