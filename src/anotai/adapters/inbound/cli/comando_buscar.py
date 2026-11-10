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
from anotai.domain.exceptions.ErroBusca import ErroBusca


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

    # 1. Resolução da aula
    aula = repo_aula.buscar_por_id(args.id_aula)
    if aula is None:
        aulas = repo_aula.listar()
        matches_aula = [
            a
            for a in aulas
            if args.id_aula in a.id_aula or args.id_aula.lower() in a.titulo.lower()
        ]
        if len(matches_aula) == 1:
            aula = matches_aula[0]
        elif len(matches_aula) > 1:
            print(f"Múltiplas aulas encontradas para '{args.id_aula}':", file=sys.stderr)
            for m in matches_aula:
                print(f"  - {m.id_aula} ({m.titulo})", file=sys.stderr)
            return 1
        else:
            print(f"Aula '{args.id_aula}' não encontrada no banco de dados.", file=sys.stderr)
            return 1

    # 2. Resolução do documento
    documento = repo_doc.buscar_por_id(args.id_documento)
    if documento is None:
        docs = repo_doc.listar()
        matches_doc = [
            d
            for d in docs
            if args.id_documento in d.id_documento or args.id_documento.lower() in d.titulo.lower()
        ]
        if len(matches_doc) == 1:
            documento = matches_doc[0]
        elif len(matches_doc) > 1:
            print(f"Múltiplos documentos encontrados para '{args.id_documento}':", file=sys.stderr)
            for md in matches_doc:
                print(f"  - {md.id_documento} ({md.titulo})", file=sys.stderr)
            return 1
        else:
            print(
                f"Documento '{args.id_documento}' não encontrado no banco de dados.",
                file=sys.stderr,
            )
            return 1

    # 3. Construção dos índices de busca conforme estratégia
    if args.strategy == "bm25":
        idx_paginas = IndiceBM25()
        idx_unidades = IndiceBM25()
    elif args.strategy in ("embedding", "hybrid"):
        modelo_emb = args.model or settings.embedding_model
        provedor = ProvedorEmbeddingOllama(
            cliente=Client(host=settings.ollama_url),
            modelo=modelo_emb,
            manter_vivo=settings.ollama_keep_alive,
        )
        if args.strategy == "embedding":
            idx_paginas = IndiceEmbeddings(provedor)
            idx_unidades = IndiceEmbeddings(provedor)
        else:
            idx_paginas = IndiceHibrido(IndiceBM25(), IndiceEmbeddings(provedor))
            idx_unidades = IndiceHibrido(IndiceBM25(), IndiceEmbeddings(provedor))

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
