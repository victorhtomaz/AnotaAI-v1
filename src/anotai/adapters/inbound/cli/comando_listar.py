import argparse
import json
import sys
from pathlib import Path
from typing import Any

from anotai.bootstrap import obter_classes_repositorios
from anotai.config import Settings


def configurar_parser_listar(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "listar",
        help="Lista todas as aulas, documentos e alinhamentos armazenados no banco.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Formato de saída.",
    )


def executar_comando_listar(
    args: argparse.Namespace,
    settings: Settings,
    repo_aula_cls: Any = None,
    repo_doc_cls: Any = None,
    repo_alin_cls: Any = None,
) -> int:
    banco_path = Path(settings.database_path)
    if not banco_path.exists():
        print("Banco de dados ainda não inicializado. Nenhum item cadastrado.", file=sys.stderr)
        return 0

    padrao_doc_cls, padrao_aula_cls, padrao_alin_cls = obter_classes_repositorios()
    repo_aula = (repo_aula_cls or padrao_aula_cls)(banco_path)
    repo_doc = (repo_doc_cls or padrao_doc_cls)(banco_path)
    repo_alin = (repo_alin_cls or padrao_alin_cls)(banco_path)

    aulas = repo_aula.listar()
    documentos = repo_doc.listar()

    # Coleta alinhamentos agrupados por aula
    alinhamentos_por_aula: dict[str, list[Any]] = {}
    for aula in aulas:
        alins = repo_alin.listar_por_aula(aula.id_aula)
        if alins:
            alinhamentos_por_aula[aula.id_aula] = alins

    if getattr(args, "format", "text") == "json":
        saida_json = {
            "aulas": [
                {
                    "id": a.id_aula,
                    "titulo": a.titulo,
                    "duracao": a.metadados.duracao,
                    "quantidade_intervalos": len(a.intervalos),
                    "quantidade_segmentos": len(a.segmentos),
                    "arquivo": a.caminho_arquivo.name,
                }
                for a in aulas
            ],
            "documentos": [
                {
                    "id": d.id_documento,
                    "titulo": d.titulo,
                    "quantidade_paginas": len(d.paginas),
                    "quantidade_unidades": sum(len(p.unidades) for p in d.paginas),
                    "arquivo": Path(d.uri_origem).name,
                }
                for d in documentos
            ],
            "alinhamentos": {
                id_aula: [
                    {
                        "id": al.id_alinhamento,
                        "estrategia": al.estrategia,
                        "origem": al.origem,
                        "status": al.status,
                        "confianca": al.confianca,
                    }
                    for al in lista
                ]
                for id_aula, lista in alinhamentos_por_aula.items()
            },
        }
        print(json.dumps(saida_json, ensure_ascii=False, indent=2))
        return 0

    print("=" * 80)
    print("AnotaAI — Itens Armazenados no Banco de Dados")
    print(f"Banco: {banco_path}")
    print("=" * 80)

    print(f"\nAULAS ({len(aulas)}):")
    if not aulas:
        print("  (nenhuma aula cadastrada. Use 'anotai transcrever <audio>')")
    for a in aulas:
        print(
            f"  • {a.id_aula} — \"{a.titulo}\" "
            f"({a.metadados.duracao:.1f}s | {len(a.intervalos)} intervalos)"
        )

    print(f"\nDOCUMENTOS ({len(documentos)}):")
    if not documentos:
        print("  (nenhum documento cadastrado. Use 'anotai pdf <arquivo>')")
    for d in documentos:
        n_unidades = sum(len(p.unidades) for p in d.paginas)
        print(
            f"  • {d.id_documento} — \"{d.titulo}\" "
            f"({len(d.paginas)} páginas | {n_unidades} unidades)"
        )

    total_alinhamentos = sum(len(lista) for lista in alinhamentos_por_aula.values())
    print(f"\nALINHAMENTOS SALVOS ({total_alinhamentos}):")
    if not alinhamentos_por_aula:
        print("  (nenhum alinhamento salvo. Use 'anotai alinhar')")
    else:
        for id_aula, alins in alinhamentos_por_aula.items():
            estrategias = sorted(set(a.estrategia for a in alins))
            est_str = ", ".join(estrategias)
            print(f"  • Aula {id_aula}: {len(alins)} registros (estratégias: {est_str})")

    print("=" * 80)
    return 0
