import argparse
import sys
from pathlib import Path
from typing import Any

from anotai.adapters.inbound.cli.comando_buscar import resolver_aula_cli
from anotai.adapters.inbound.cli.formatador_terminal import formatar_aula_texto
from anotai.bootstrap import obter_classes_repositorios
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
    repo_cls: Any = None,
) -> int:
    _, padrao_aula_cls, _ = obter_classes_repositorios()
    repo_aula_cls = repo_cls or padrao_aula_cls
    repositorio = repo_aula_cls(Path(settings.database_path))
    aula = resolver_aula_cli(repositorio, args.id_aula)
    if aula is None:
        return 1

    if args.intervalo is not None and not any(i.ordem == args.intervalo for i in aula.intervalos):
        print(
            f"Aviso: Intervalo explicativo #{args.intervalo} não encontrado na aula.",
            file=sys.stderr,
        )
        return 1

    print(formatar_aula_texto(aula, detalhado=args.verbose, intervalo_alvo=args.intervalo))
    return 0
