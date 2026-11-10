from pathlib import Path

import pytest

from anotai.adapters.outbound.persistence import (
    RepositorioAlinhamentoSQLite,
    RepositorioAnotacaoSQLite,
    RepositorioAulaSQLite,
    RepositorioDocumento,
)
from anotai.domain.entities.Alinhamento import Alinhamento
from anotai.domain.entities.Anotacao import Anotacao
from anotai.domain.entities.Aula import Aula
from anotai.domain.entities.Documento import Documento, PaginaDocumento, UnidadeDocumento
from anotai.domain.entities.IntervaloExplicativo import IntervaloExplicativo
from anotai.domain.entities.SegmentoTranscricao import SegmentoTranscricao
from anotai.domain.entities.ValidadorIntegridade import ValidadorIntegridade
from anotai.domain.exceptions.ErroIntegridade import ErroIntegridade
from anotai.domain.value_objects.CaixaDelimitadora import CaixaDelimitadora
from anotai.domain.value_objects.IntervaloTempo import IntervaloTempo
from anotai.domain.value_objects.MetadadosAudio import MetadadosAudio
from anotai.domain.value_objects.ProvenienciaDocumento import ProvenienciaDocumento
from anotai.domain.value_objects.TipoRelacao import (
    OrigemAlinhamento,
    StatusAlinhamento,
    TipoRelacao,
)


def _criar_documento_teste(id_doc: str = "doc-1", com_decorativa: bool = False) -> Documento:
    unidades_pag1 = [
        UnidadeDocumento(
            id_unidade=f"{id_doc}-p1-u1",
            id_documento=id_doc,
            id_pagina=f"{id_doc}-p1",
            tipo="title",
            texto="Introdução à Inteligência Artificial",
            ordem_leitura=1,
            caixa=CaixaDelimitadora(10.0, 10.0, 200.0, 30.0),
            fonte="native",
        ),
        UnidadeDocumento(
            id_unidade=f"{id_doc}-p1-u2",
            id_documento=id_doc,
            id_pagina=f"{id_doc}-p1",
            tipo="paragraph",
            texto="Conceitos fundamentais de aprendizado supervisionado.",
            ordem_leitura=2,
            caixa=CaixaDelimitadora(10.0, 40.0, 300.0, 100.0),
            fonte="native",
        ),
    ]

    if com_decorativa:
        unidades_pag1.append(
            UnidadeDocumento(
                id_unidade=f"{id_doc}-p1-u-decorativa",
                id_documento=id_doc,
                id_pagina=f"{id_doc}-p1",
                tipo="figure",
                texto=None,
                ordem_leitura=3,
                caixa=CaixaDelimitadora(500.0, 10.0, 550.0, 60.0),
                fonte="native",
                eh_decorativa=True,
            )
        )

    unidades_pag2 = [
        UnidadeDocumento(
            id_unidade=f"{id_doc}-p2-u1",
            id_documento=id_doc,
            id_pagina=f"{id_doc}-p2",
            tipo="formula",
            texto="y = Wx + b",
            ordem_leitura=1,
            caixa=CaixaDelimitadora(50.0, 100.0, 150.0, 130.0),
            fonte="native",
        )
    ]

    paginas = [
        PaginaDocumento(
            id_pagina=f"{id_doc}-p1",
            numero_pagina=1,
            texto_nativo="Introdução à Inteligência Artificial...",
            texto_normalizado="Introdução à Inteligência Artificial...",
            metodo_extracao="native",
            unidades=unidades_pag1,
        ),
        PaginaDocumento(
            id_pagina=f"{id_doc}-p2",
            numero_pagina=2,
            texto_nativo="y = Wx + b",
            texto_normalizado="y = Wx + b",
            metodo_extracao="native",
            unidades=unidades_pag2,
        ),
    ]

    return Documento(
        id_documento=id_doc,
        uri_origem=f"/dados/{id_doc}.pdf",
        titulo=f"Material {id_doc}",
        paginas=paginas,
        versao_processamento="fase3-v1",
        proveniencia=ProvenienciaDocumento(
            uri_origem=f"/dados/{id_doc}.pdf",
            metodo_extracao="native",
            versao_pipeline="fase3-v1",
        ),
    )


def _criar_aula_teste(id_aula: str = "aula-1") -> Aula:
    seg1 = SegmentoTranscricao(
        id_segmento=f"seg-{id_aula}-0001",
        id_aula=id_aula,
        texto="Hoje falaremos sobre inteligência artificial e aprendizado supervisionado.",
        intervalo=IntervaloTempo(0.0, 5.0),
        ordem=1,
    )
    seg2 = SegmentoTranscricao(
        id_segmento=f"seg-{id_aula}-0002",
        id_aula=id_aula,
        texto="Vejamos a equação do modelo linear na próxima página.",
        intervalo=IntervaloTempo(5.5, 12.0),
        ordem=2,
    )
    seg3 = SegmentoTranscricao(
        id_segmento=f"seg-{id_aula}-0003",
        id_aula=id_aula,
        texto="Aqui temos um aviso administrativo sobre a prova.",
        intervalo=IntervaloTempo(13.0, 20.0),
        ordem=3,
    )

    inter1 = IntervaloExplicativo(
        id_intervalo=f"interval-{id_aula}-0001",
        id_aula=id_aula,
        texto="Hoje falaremos sobre inteligência artificial e aprendizado supervisionado.",
        intervalo=IntervaloTempo(0.0, 5.0),
        ordem=1,
        ids_segmentos=[seg1.id_segmento],
        tipo="explanation",
    )
    inter2 = IntervaloExplicativo(
        id_intervalo=f"interval-{id_aula}-0002",
        id_aula=id_aula,
        texto="Vejamos a equação do modelo linear na próxima página.",
        intervalo=IntervaloTempo(5.5, 12.0),
        ordem=2,
        ids_segmentos=[seg2.id_segmento],
        tipo="explanation",
    )
    inter3 = IntervaloExplicativo(
        id_intervalo=f"interval-{id_aula}-0003",
        id_aula=id_aula,
        texto="Aqui temos um aviso administrativo sobre a prova.",
        intervalo=IntervaloTempo(13.0, 20.0),
        ordem=3,
        ids_segmentos=[seg3.id_segmento],
        tipo="reference",
    )

    return Aula(
        id_aula=id_aula,
        titulo=f"Gravação {id_aula}",
        uri_origem=f"/dados/{id_aula}.wav",
        caminho_arquivo=Path(f"/dados/{id_aula}.wav"),
        metadados=MetadadosAudio(
            duracao=25.0,
            taxa_amostragem=16000,
            canais=1,
            formato="wav",
        ),
        segmentos=[seg1, seg2, seg3],
        intervalos=[inter1, inter2, inter3],
        idioma="pt",
    )


# --- Testes de Value Objects ---


def test_tipo_relacao_normalizacao() -> None:
    assert TipoRelacao.normalizar("direct") == TipoRelacao.DIRETA
    assert TipoRelacao.normalizar("direta") == TipoRelacao.DIRETA
    assert TipoRelacao.normalizar("explanation") == TipoRelacao.DIRETA
    assert TipoRelacao.normalizar("explicacao_direta") == TipoRelacao.DIRETA

    assert TipoRelacao.normalizar("reference") == TipoRelacao.REFERENCIA
    assert TipoRelacao.normalizar("referencia") == TipoRelacao.REFERENCIA

    assert TipoRelacao.normalizar("contextual") == TipoRelacao.CONTEXTUAL
    assert TipoRelacao.normalizar("contextualization") == TipoRelacao.CONTEXTUAL
    assert TipoRelacao.normalizar("contextualizacao") == TipoRelacao.CONTEXTUAL

    assert TipoRelacao.normalizar(None) is None

    with pytest.raises(ValueError):
        TipoRelacao.normalizar("desconhecido")


def test_status_alinhamento_normalizacao() -> None:
    assert StatusAlinhamento.normalizar("aligned") == StatusAlinhamento.ALINHADO
    assert StatusAlinhamento.normalizar("abstained") == StatusAlinhamento.ABSTIDO

    with pytest.raises(ValueError):
        StatusAlinhamento.normalizar("invalido")


def test_origem_alinhamento_normalizacao() -> None:
    assert OrigemAlinhamento.normalizar("automatic") == OrigemAlinhamento.AUTOMATICO
    assert OrigemAlinhamento.normalizar("manual") == OrigemAlinhamento.MANUAL

    with pytest.raises(ValueError):
        OrigemAlinhamento.normalizar("invalido")


# --- Testes de Entidade Alinhamento ---


def test_alinhamento_criacao_valida_multi_rotulo() -> None:
    alinhamento = Alinhamento(
        id_alinhamento="align-001",
        id_aula="aula-1",
        id_documento="doc-1",
        id_intervalo="interval-aula-1-0001",
        ids_paginas=["doc-1-p1", "doc-1-p2", "doc-1-p1"],  # deduplica
        ids_unidades=["doc-1-p1-u1", "doc-1-p1-u2"],
        status="aligned",
        tipo_relacao="explanation",
        confianca=0.85,
        estrategia="hierarchical",
        ids_evidencias=["ev1", "ev2"],
    )

    assert alinhamento.ids_paginas == ["doc-1-p1", "doc-1-p2"]
    assert alinhamento.tipo_relacao == "direct"
    assert alinhamento.status == "aligned"
    assert alinhamento.confianca == 0.85


def test_alinhamento_abstenção_valida() -> None:
    alinhamento = Alinhamento(
        id_alinhamento="align-abst-001",
        id_aula="aula-1",
        id_documento="doc-1",
        id_intervalo="interval-aula-1-0003",
        ids_paginas=[],
        ids_unidades=[],
        status="abstained",
        confianca=0.1,
        estrategia="bm25",
        justificativa="Aviso administrativo sem correspondência no material didático",
    )

    assert alinhamento.status == "abstained"
    assert alinhamento.ids_paginas == []
    assert alinhamento.ids_unidades == []
    assert alinhamento.tipo_relacao is None
    assert alinhamento.justificativa is not None


def test_alinhamento_invariantes_invalidas() -> None:
    # Alinhado sem página
    with pytest.raises(ValueError, match="ao menos uma página"):
        Alinhamento(
            id_alinhamento="a1",
            id_aula="au1",
            id_documento="d1",
            id_intervalo="i1",
            ids_paginas=[],
            status="aligned",
        )

    # Abstido com páginas
    with pytest.raises(ValueError, match="não deve conter páginas"):
        Alinhamento(
            id_alinhamento="a2",
            id_aula="au1",
            id_documento="d1",
            id_intervalo="i1",
            ids_paginas=["p1"],
            status="abstained",
        )

    # Confiança inválida
    with pytest.raises(ValueError, match="confiança"):
        Alinhamento(
            id_alinhamento="a3",
            id_aula="au1",
            id_documento="d1",
            id_intervalo="i1",
            ids_paginas=["p1"],
            confianca=1.5,
        )


def test_alinhamento_gerar_id_estavel() -> None:
    id1 = Alinhamento.gerar_id_estavel("int-1", "doc-1", "bm25", "automatic")
    id2 = Alinhamento.gerar_id_estavel("int-1", "doc-1", "bm25", "automatic")
    id3 = Alinhamento.gerar_id_estavel("int-1", "doc-1", "embedding", "automatic")

    assert id1 == id2
    assert id1 != id3
    assert id1.startswith("align-")


# --- Testes de Entidade Anotacao ---


def test_anotacao_ground_truth() -> None:
    anotacao = Anotacao(
        id_anotacao="annot-001",
        id_aula="aula-1",
        id_documento="doc-1",
        intervalo=IntervaloTempo(0.0, 5.0),
        id_intervalo="interval-aula-1-0001",
        ids_paginas=["doc-1-p1", "doc-1-p2"],
        ids_unidades=["doc-1-p1-u1"],
        tipo_relacao="explicacao_direta",
        notas="Anotação de teste",
    )

    assert anotacao.tipo_relacao == "direct"
    assert anotacao.ids_paginas == ["doc-1-p1", "doc-1-p2"]

    # Caso negativo de ground truth (sem correspondência)
    anotacao_negativa = Anotacao(
        id_anotacao="annot-neg-001",
        id_aula="aula-1",
        id_documento="doc-1",
        intervalo=IntervaloTempo(13.0, 20.0),
        id_intervalo="interval-aula-1-0003",
        ids_paginas=[],
        ids_unidades=[],
        tipo_relacao=None,
        notas="Trecho sem conteúdo no PDF",
    )
    assert anotacao_negativa.ids_paginas == []
    assert anotacao_negativa.ids_unidades == []


# --- Testes de ValidadorIntegridade ---


def test_validador_integridade_sucesso() -> None:
    doc = _criar_documento_teste("doc-1")
    aula = _criar_aula_teste("aula-1")

    ValidadorIntegridade.validar_documento(doc)
    ValidadorIntegridade.validar_aula(aula)

    alinhamento = Alinhamento(
        id_alinhamento="al-1",
        id_aula=aula.id_aula,
        id_documento=doc.id_documento,
        id_intervalo=aula.intervalos[0].id_intervalo,
        ids_paginas=[doc.paginas[0].id_pagina],
        ids_unidades=[doc.paginas[0].unidades[0].id_unidade],
        status="aligned",
        tipo_relacao="direct",
    )
    ValidadorIntegridade.validar_alinhamento(alinhamento, aula=aula, documento=doc)


def test_validador_integridade_inconsistencias() -> None:
    doc = _criar_documento_teste("doc-1", com_decorativa=True)
    aula = _criar_aula_teste("aula-1")

    # Alinhamento com página pertencente a outro documento
    al_pag_invalida = Alinhamento(
        id_alinhamento="al-inv-1",
        id_aula=aula.id_aula,
        id_documento=doc.id_documento,
        id_intervalo=aula.intervalos[0].id_intervalo,
        ids_paginas=["pagina-inexistente"],
        status="aligned",
        tipo_relacao="direct",
    )
    with pytest.raises(ErroIntegridade, match="não pertence ao documento"):
        ValidadorIntegridade.validar_alinhamento(al_pag_invalida, documento=doc)

    # Alinhamento com unidade decorativa
    unidade_decorativa = doc.paginas[0].unidades[2]
    al_decorativa = Alinhamento(
        id_alinhamento="al-inv-2",
        id_aula=aula.id_aula,
        id_documento=doc.id_documento,
        id_intervalo=aula.intervalos[0].id_intervalo,
        ids_paginas=[doc.paginas[0].id_pagina],
        ids_unidades=[unidade_decorativa.id_unidade],
        status="aligned",
        tipo_relacao="direct",
    )
    with pytest.raises(ErroIntegridade, match="marcada como decorativa"):
        ValidadorIntegridade.validar_alinhamento(al_decorativa, documento=doc)

    # Inconsistência hierárquica: unidade presente, mas página da unidade ausente em ids_paginas
    al_hierarquia = Alinhamento(
        id_alinhamento="al-inv-3",
        id_aula=aula.id_aula,
        id_documento=doc.id_documento,
        id_intervalo=aula.intervalos[0].id_intervalo,
        ids_paginas=[doc.paginas[0].id_pagina],
        # unidade da p2, mas p2 não está em ids_paginas:
        ids_unidades=[doc.paginas[1].unidades[0].id_unidade],
        status="aligned",
        tipo_relacao="direct",
    )
    with pytest.raises(ErroIntegridade, match="Inconsistência hierárquica"):
        ValidadorIntegridade.validar_alinhamento(al_hierarquia, documento=doc)


# --- Testes de Persistência SQLite ---


def test_repositorio_documento_salvar_buscar_listar(tmp_path: Path) -> None:
    caminho_banco = tmp_path / "teste_doc.sqlite"
    repo = RepositorioDocumento(caminho_banco)

    doc = _criar_documento_teste("doc-100")
    repo.salvar(doc)

    assert repo.existe("doc-100")
    assert not repo.existe("doc-nao-existe")

    recuperado = repo.buscar_por_id("doc-100")
    assert recuperado is not None
    assert recuperado.id_documento == "doc-100"
    assert len(recuperado.paginas) == 2
    assert len(recuperado.paginas[0].unidades) == 2
    assert recuperado.paginas[0].unidades[0].texto == "Introdução à Inteligência Artificial"
    assert recuperado.paginas[0].unidades[0].caixa is not None
    assert recuperado.paginas[0].unidades[0].caixa.x0 == 10.0

    todos = repo.listar()
    assert len(todos) == 1
    assert todos[0].id_documento == "doc-100"

    # Reprocessamento idempotente de documento: salvar novamente com alteração
    doc.titulo = "Material 100 Atualizado"
    doc.paginas[0].texto_normalizado = "Texto atualizado"
    repo.salvar(doc)

    atualizado = repo.buscar_por_id("doc-100")
    assert atualizado is not None
    assert atualizado.titulo == "Material 100 Atualizado"
    assert atualizado.paginas[0].texto_normalizado == "Texto atualizado"
    assert len(repo.listar()) == 1  # Sem duplicatas


def test_repositorio_alinhamento_e_navegacao_bidirecional(tmp_path: Path) -> None:
    caminho_banco = tmp_path / "anotai.sqlite"
    repo_doc = RepositorioDocumento(caminho_banco)
    repo_aula = RepositorioAulaSQLite(caminho_banco)
    repo_align = RepositorioAlinhamentoSQLite(caminho_banco)

    doc = _criar_documento_teste("doc-1")
    aula = _criar_aula_teste("aula-1")

    repo_doc.salvar(doc)
    repo_aula.salvar(aula)

    # 1. Alinhamento multi-rótulo e hierárquico (Intervalo 1 -> P1 com 2 unidades, P2 com 1 unidade)
    align1 = Alinhamento(
        id_alinhamento="align-01",
        id_aula=aula.id_aula,
        id_documento=doc.id_documento,
        id_intervalo=aula.intervalos[0].id_intervalo,
        ids_paginas=[doc.paginas[0].id_pagina, doc.paginas[1].id_pagina],
        ids_unidades=[doc.paginas[0].unidades[0].id_unidade, doc.paginas[1].unidades[0].id_unidade],
        status="aligned",
        tipo_relacao="direct",
        confianca=0.92,
        estrategia="hierarchical",
        ids_evidencias=["ev-1"],
    )

    # 2. Alinhamento que revisita a P1 (Intervalo 2 -> P1)
    align2 = Alinhamento(
        id_alinhamento="align-02",
        id_aula=aula.id_aula,
        id_documento=doc.id_documento,
        id_intervalo=aula.intervalos[1].id_intervalo,
        ids_paginas=[doc.paginas[0].id_pagina],
        ids_unidades=[doc.paginas[0].unidades[1].id_unidade],
        status="aligned",
        tipo_relacao="reference",
        confianca=0.75,
        estrategia="hierarchical",
    )

    # 3. Alinhamento com abstenção explícita (Intervalo 3 -> abstained)
    align3 = Alinhamento(
        id_alinhamento="align-03",
        id_aula=aula.id_aula,
        id_documento=doc.id_documento,
        id_intervalo=aula.intervalos[2].id_intervalo,
        ids_paginas=[],
        ids_unidades=[],
        status="abstained",
        confianca=0.05,
        estrategia="bm25",
        justificativa="Aviso administrativo sem correspondência",
    )

    repo_align.salvar_lote([align1, align2, align3])

    # Verificação de busca por ID
    recuperado = repo_align.buscar_por_id("align-01")
    assert recuperado is not None
    assert recuperado.id_alinhamento == "align-01"
    assert recuperado.ids_paginas == [doc.paginas[0].id_pagina, doc.paginas[1].id_pagina]
    assert len(recuperado.ids_unidades) == 2
    assert recuperado.confianca == 0.92

    # Verificação da abstenção recuperada
    recuperado_abst = repo_align.buscar_por_id("align-03")
    assert recuperado_abst is not None
    assert recuperado_abst.status == "abstained"
    assert recuperado_abst.ids_paginas == []
    assert recuperado_abst.ids_unidades == []
    assert recuperado_abst.justificativa == "Aviso administrativo sem correspondência"

    # Navegação áudio -> PDF (listar por intervalo)
    aligns_int1 = repo_align.listar_por_intervalo(aula.intervalos[0].id_intervalo)
    assert len(aligns_int1) == 1
    assert aligns_int1[0].id_alinhamento == "align-01"

    # Navegação PDF -> áudio (listar por página)
    aligns_p1 = repo_align.listar_por_pagina(doc.paginas[0].id_pagina)
    assert len(aligns_p1) == 2  # Intervalo 1 e Intervalo 2 associados à Página 1!

    # Navegação PDF -> áudio (listar por unidade)
    aligns_u1 = repo_align.listar_por_unidade(doc.paginas[0].unidades[0].id_unidade)
    assert len(aligns_u1) == 1
    assert aligns_u1[0].id_intervalo == aula.intervalos[0].id_intervalo

    # Reprocessamento idempotente: re-executar com mesma chave substitui
    align1_reprocessado = Alinhamento(
        id_alinhamento="align-01-novo-id",
        id_aula=aula.id_aula,
        id_documento=doc.id_documento,
        id_intervalo=aula.intervalos[0].id_intervalo,
        ids_paginas=[doc.paginas[0].id_pagina],
        ids_unidades=[doc.paginas[0].unidades[0].id_unidade],
        status="aligned",
        tipo_relacao="direct",
        confianca=0.98,
        estrategia="hierarchical",  # mesma tupla (int0, doc, hierarchical, automatic)
        origem="automatic",
    )
    repo_align.salvar(align1_reprocessado)

    aligns_int1_depois = repo_align.listar_por_intervalo(aula.intervalos[0].id_intervalo)
    assert len(aligns_int1_depois) == 1
    assert aligns_int1_depois[0].confianca == 0.98
    assert len(aligns_int1_depois[0].ids_paginas) == 1


def test_repositorio_alinhamento_rejeita_referencias_invalidas(tmp_path: Path) -> None:
    caminho_banco = tmp_path / "anotai.sqlite"
    repo_doc = RepositorioDocumento(caminho_banco)
    repo_aula = RepositorioAulaSQLite(caminho_banco)
    repo_align = RepositorioAlinhamentoSQLite(caminho_banco)

    doc = _criar_documento_teste("doc-1", com_decorativa=True)
    aula = _criar_aula_teste("aula-1")
    repo_doc.salvar(doc)
    repo_aula.salvar(aula)

    # Aula inexistente
    al_aula_invalida = Alinhamento(
        id_alinhamento="al-x",
        id_aula="aula-inexistente",
        id_documento="doc-1",
        id_intervalo=aula.intervalos[0].id_intervalo,
        ids_paginas=[doc.paginas[0].id_pagina],
        status="aligned",
        tipo_relacao="direct",
    )
    with pytest.raises(ErroIntegridade, match="Falha de integridade referencial"):
        repo_align.salvar(al_aula_invalida)

    # Página inexistente no documento
    al_pag_invalida = Alinhamento(
        id_alinhamento="al-y",
        id_aula=aula.id_aula,
        id_documento=doc.id_documento,
        id_intervalo=aula.intervalos[0].id_intervalo,
        ids_paginas=["pagina-fantasma"],
        status="aligned",
        tipo_relacao="direct",
    )
    with pytest.raises(ErroIntegridade, match="Falha de integridade referencial"):
        repo_align.salvar(al_pag_invalida)

    # Unidade decorativa
    unidade_decorativa = doc.paginas[0].unidades[2]
    al_decorativa = Alinhamento(
        id_alinhamento="al-z",
        id_aula=aula.id_aula,
        id_documento=doc.id_documento,
        id_intervalo=aula.intervalos[0].id_intervalo,
        ids_paginas=[doc.paginas[0].id_pagina],
        ids_unidades=[unidade_decorativa.id_unidade],
        status="aligned",
        tipo_relacao="direct",
    )
    with pytest.raises(ErroIntegridade, match="marcada como decorativa"):
        repo_align.salvar(al_decorativa)


def test_repositorio_anotacao_ground_truth(tmp_path: Path) -> None:
    caminho_banco = tmp_path / "anotai.sqlite"
    repo_doc = RepositorioDocumento(caminho_banco)
    repo_aula = RepositorioAulaSQLite(caminho_banco)
    repo_anotacao = RepositorioAnotacaoSQLite(caminho_banco)

    doc = _criar_documento_teste("doc-1")
    aula = _criar_aula_teste("aula-1")
    repo_doc.salvar(doc)
    repo_aula.salvar(aula)

    anotacao1 = Anotacao(
        id_anotacao="anot-01",
        id_aula=aula.id_aula,
        id_documento=doc.id_documento,
        intervalo=IntervaloTempo(0.0, 5.0),
        id_intervalo=aula.intervalos[0].id_intervalo,
        ids_paginas=[doc.paginas[0].id_pagina],
        ids_unidades=[doc.paginas[0].unidades[0].id_unidade],
        tipo_relacao="direct",
        notas="Anotador A: explicação clara do título",
        versao="gt-v1",
    )

    anotacao2 = Anotacao(
        id_anotacao="anot-02",
        id_aula=aula.id_aula,
        id_documento=doc.id_documento,
        intervalo=IntervaloTempo(13.0, 20.0),
        id_intervalo=aula.intervalos[2].id_intervalo,
        ids_paginas=[],
        ids_unidades=[],
        tipo_relacao=None,
        notas="Aviso administrativo - sem correspondência",
        versao="gt-v1",
    )

    repo_anotacao.salvar_lote([anotacao1, anotacao2])

    rec1 = repo_anotacao.buscar_por_id("anot-01")
    assert rec1 is not None
    assert rec1.id_anotacao == "anot-01"
    assert rec1.ids_paginas == [doc.paginas[0].id_pagina]
    assert rec1.ids_unidades == [doc.paginas[0].unidades[0].id_unidade]

    rec2 = repo_anotacao.buscar_por_id("anot-02")
    assert rec2 is not None
    assert rec2.ids_paginas == []

    # Listar por aula
    da_aula = repo_anotacao.listar_por_aula(aula.id_aula, versao="gt-v1")
    assert len(da_aula) == 2

    # Listar por intervalo
    do_intervalo = repo_anotacao.listar_por_intervalo(aula.intervalos[0].id_intervalo)
    assert len(do_intervalo) == 1
    assert do_intervalo[0].id_anotacao == "anot-01"
