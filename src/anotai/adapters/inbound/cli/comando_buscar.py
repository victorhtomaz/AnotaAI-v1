import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ollama import Client

from anotai.adapters.inbound.cli.formatador_terminal import formatar_recuperacao_texto
from anotai.adapters.outbound.ollama.provedor_embedding import ProvedorEmbeddingOllama
from anotai.adapters.outbound.persistence import RepositorioAulaSQLite, RepositorioDocumento
from anotai.adapters.outbound.search import IndiceBM25, IndiceEmbeddings, IndiceHibrido
from anotai.application.use_cases.recuperar_candidatos import RecuperarCandidatos
from anotai.config import Settings
from anotai.domain.exceptions import ErroBusca


def configurar_parser_buscar(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "buscar",
        help="Recupera candidatos de páginas e unidades para os intervalos de uma aula.",
    )
    parser.add_argument("id_aula", type=str, help="ID ou parte do título da aula.")
    parser.add_argument("id_documento", type=str, help="ID ou parte do título do documento.")
    parser.add_argument(
        "--strategy",
        choices=("bm25", "embedding", "hybrid"),
        default="bm25",
        help="Estratégia de recuperação textual/semântica.",
    )
    parser.add_argument(
        "--top-k-paginas",
        type=int,
        default=5,
        help="Quantidade máxima de páginas candidatas por intervalo.",
    )
    parser.add_argument(
        "--top-k-unidades",
        type=int,
        default=5,
        help="Quantidade máxima de unidades candidatas por intervalo.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Limiar mínimo de confiança para abstenção.",
    )
    parser.add_argument(
        "--intervalo",
        type=int,
        default=None,
        help="Número de ordem de um intervalo explicativo específico.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Formato de saída.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Modelo de embedding Ollama (usado se strategy for embedding ou hybrid).",
    )


def resolver_aula_cli(repo_aula: Any, termo_id: str | None) -> Any | None:
    aulas = repo_aula.listar()
    if termo_id is None:
        if len(aulas) == 1:
            return aulas[0]
        if not aulas:
            print(
                "Nenhuma aula cadastrada no banco. Use 'anotai transcrever <audio>' primeiro.",
                file=sys.stderr,
            )
            return None
        print("Múltiplas aulas disponíveis no banco. Especifique uma:", file=sys.stderr)
        for a in aulas:
            print(f"  - {a.id_aula} (\"{a.titulo}\")", file=sys.stderr)
        return None

    aula = repo_aula.buscar_por_id(termo_id)
    if aula is not None:
        return aula

    # Tenta casamento por nome de arquivo se for caminho
    nome_arquivo = Path(termo_id).name.lower()
    matches_arq = [
        a
        for a in aulas
        if Path(a.caminho_arquivo).name.lower() == nome_arquivo
        or Path(a.uri_origem).name.lower() == nome_arquivo
    ]
    if len(matches_arq) == 1:
        return matches_arq[0]

    if hasattr(repo_aula, "buscar_por_termo"):
        matches_aula_tuplas = repo_aula.buscar_por_termo(termo_id)
        if len(matches_aula_tuplas) == 1:
            return repo_aula.buscar_por_id(matches_aula_tuplas[0][0])
        if len(matches_aula_tuplas) > 1:
            print(f"Múltiplas aulas encontradas para '{termo_id}':", file=sys.stderr)
            for m_id, m_titulo in matches_aula_tuplas:
                print(f"  - {m_id} (\"{m_titulo}\")", file=sys.stderr)
            return None
        print(f"Aula '{termo_id}' não encontrada no banco de dados.", file=sys.stderr)
        return None

    matches_aula = [
        a for a in aulas if termo_id in a.id_aula or termo_id.lower() in a.titulo.lower()
    ]
    if len(matches_aula) == 1:
        return matches_aula[0]
    if len(matches_aula) > 1:
        print(f"Múltiplas aulas encontradas para '{termo_id}':", file=sys.stderr)
        for m in matches_aula:
            print(f"  - {m.id_aula} (\"{m.titulo}\")", file=sys.stderr)
        return None
    print(f"Aula '{termo_id}' não encontrada no banco de dados.", file=sys.stderr)
    return None


def resolver_documento_cli(repo_doc: Any, termo_id: str | None) -> Any | None:
    docs = repo_doc.listar()
    if termo_id is None:
        if len(docs) == 1:
            return docs[0]
        if not docs:
            print(
                "Nenhum documento cadastrado no banco. Use 'anotai pdf <arquivo>' primeiro.",
                file=sys.stderr,
            )
            return None
        print("Múltiplos documentos disponíveis no banco. Especifique um:", file=sys.stderr)
        for d in docs:
            print(f"  - {d.id_documento} (\"{d.titulo}\")", file=sys.stderr)
        return None

    documento = repo_doc.buscar_por_id(termo_id)
    if documento is not None:
        return documento

    # Tenta casamento por nome de arquivo se for caminho
    nome_arquivo = Path(termo_id).name.lower()
    matches_arq = [
        d
        for d in docs
        if Path(d.uri_origem).name.lower() == nome_arquivo
    ]
    if len(matches_arq) == 1:
        return matches_arq[0]

    if hasattr(repo_doc, "buscar_por_termo"):
        matches_doc_tuplas = repo_doc.buscar_por_termo(termo_id)
        if len(matches_doc_tuplas) == 1:
            return repo_doc.buscar_por_id(matches_doc_tuplas[0][0])
        if len(matches_doc_tuplas) > 1:
            print(f"Múltiplos documentos encontrados para '{termo_id}':", file=sys.stderr)
            for md_id, md_titulo in matches_doc_tuplas:
                print(f"  - {md_id} (\"{md_titulo}\")", file=sys.stderr)
            return None
        print(f"Documento '{termo_id}' não encontrado no banco de dados.", file=sys.stderr)
        return None

    termo = termo_id.lower()
    matches_doc = [
        d for d in docs if termo_id in d.id_documento or termo in d.titulo.lower()
    ]
    if len(matches_doc) == 1:
        return matches_doc[0]
    if len(matches_doc) > 1:
        print(f"Múltiplos documentos encontrados para '{termo_id}':", file=sys.stderr)
        for md in matches_doc:
            print(f"  - {md.id_documento} (\"{md.titulo}\")", file=sys.stderr)
        return None
    print(f"Documento '{termo_id}' não encontrado no banco de dados.", file=sys.stderr)
    return None


def construir_indices_busca(
    estrategia_base: str, settings: Settings, modelo_override: str | None = None
) -> tuple[Any, Any]:
    if estrategia_base == "bm25":
        return IndiceBM25(), IndiceBM25()

    if estrategia_base in ("embedding", "hybrid"):
        modelo_emb = modelo_override or settings.embedding_model
        provedor = ProvedorEmbeddingOllama(
            cliente=Client(host=settings.ollama_url),
            modelo=modelo_emb,
            manter_vivo=settings.ollama_keep_alive,
        )
        if estrategia_base == "embedding":
            return IndiceEmbeddings(provedor), IndiceEmbeddings(provedor)
        return (
            IndiceHibrido(IndiceBM25(), IndiceEmbeddings(provedor)),
            IndiceHibrido(IndiceBM25(), IndiceEmbeddings(provedor)),
        )

    raise ValueError(f"Estratégia base de busca não suportada: '{estrategia_base}'")


def executar_comando_buscar(
    args: argparse.Namespace,
    settings: Settings,
    repo_aula_cls: Any = RepositorioAulaSQLite,
    repo_doc_cls: Any = RepositorioDocumento,
    recuperador_cls: Any = RecuperarCandidatos,
) -> int:
    banco_path = Path(settings.database_path)
    repo_aula = repo_aula_cls(banco_path)
    repo_doc = repo_doc_cls(banco_path)

    aula = resolver_aula_cli(repo_aula, args.id_aula)
    if aula is None:
        return 1

    documento = resolver_documento_cli(repo_doc, args.id_documento)
    if documento is None:
        return 1

    idx_paginas, idx_unidades = construir_indices_busca(
        args.strategy, settings, modelo_override=args.model
    )

    limiar = args.threshold if args.threshold is not None else settings.abstention_threshold

    caso_uso = recuperador_cls(
        indice_paginas=idx_paginas,
        indice_unidades=idx_unidades,
        estrategia=args.strategy,
        top_k_paginas=args.top_k_paginas,
        top_k_unidades=args.top_k_unidades,
        limiar_abstencao=limiar,
    )

    try:
        resultados = caso_uso.executar(aula, documento)
    except ErroBusca as exc:
        print(f"Erro na recuperação documental: {exc}", file=sys.stderr)
        return 1

    if args.intervalo is not None:
        resultados_filtrados = [r for r in resultados if r.ordem_intervalo == args.intervalo]
        if not resultados_filtrados:
            print(
                f"Aviso: Intervalo explicativo #{args.intervalo} não encontrado na aula.",
                file=sys.stderr,
            )
            return 1
        resultados = resultados_filtrados

    if args.format == "json":
        saida_json = [
            {
                "id_intervalo": r.id_intervalo,
                "ordem_intervalo": r.ordem_intervalo,
                "texto_intervalo": r.texto_intervalo,
                "inicio": r.intervalo_tempo.inicio,
                "fim": r.intervalo_tempo.fim,
                "abstido": r.abstido,
                "motivo_abstencao": r.motivo_abstencao,
                "maior_pontuacao": r.maior_pontuacao,
                "candidatos_pagina": [
                    {
                        "id_pagina": cp.id_pagina,
                        "numero_pagina": cp.numero_pagina,
                        "pontuacao": cp.pontuacao,
                        "pontuacao_direta": cp.pontuacao_direta,
                        "pontuacao_unidades": cp.pontuacao_unidades,
                    }
                    for cp in r.candidatos_pagina
                ],
                "candidatos_unidade": [
                    {
                        "id_unidade": cu.id_unidade,
                        "id_pagina": cu.id_pagina,
                        "numero_pagina": cu.numero_pagina,
                        "tipo": cu.tipo_unidade,
                        "ordem": cu.ordem_leitura,
                        "pontuacao": cu.pontuacao,
                        "texto": cu.texto,
                    }
                    for cu in r.candidatos_unidade
                ],
            }
            for r in resultados
        ]
        print(json.dumps(saida_json, ensure_ascii=False, indent=2))
    else:
        print(formatar_recuperacao_texto(aula, documento, resultados))

    return 0
