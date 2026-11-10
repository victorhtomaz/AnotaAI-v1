import argparse
import sys
from pathlib import Path
from typing import Any

from anotai.adapters.inbound.cli.formatador_terminal import formatar_aula_texto
from anotai.adapters.outbound.persistence import RepositorioAulaSQLite
from anotai.config import Settings


def configurar_parser_exibir(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "exibir", help="Exibe transcrição e intervalos de uma aula persistida."
    )
    parser.add_argument("id_aula", type=str, help="ID ou parte do título da aula.")
    parser.add_argument(
        "--intervalo",
        type=int,
        default=None,
        help="Número do intervalo explicativo específico para inspecionar.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Exibe segmentos atômicos.",
    )


def executar_comando_exibir(
    args: argparse.Namespace,
    settings: Settings,
    repo_cls: Any = RepositorioAulaSQLite,
) -> int:
    repositorio = repo_cls(Path(settings.database_path))
    aula = repositorio.buscar_por_id(args.id_aula)
    if aula is None:
        aulas = repositorio.listar()
        matches = [
            a
            for a in aulas
            if args.id_aula in a.id_aula or args.id_aula.lower() in a.titulo.lower()
        ]
        if len(matches) == 1:
            aula = matches[0]
        elif len(matches) > 1:
            print(f"Múltiplas aulas encontradas para '{args.id_aula}':", file=sys.stderr)
            for m in matches:
                print(f"  - {m.id_aula} ({m.titulo})", file=sys.stderr)
            return 1
        else:
            print(f"Aula '{args.id_aula}' não encontrada no banco de dados.", file=sys.stderr)
            return 1

    print(formatar_aula_texto(aula, detalhado=args.verbose, intervalo_alvo=args.intervalo))
    return 0
