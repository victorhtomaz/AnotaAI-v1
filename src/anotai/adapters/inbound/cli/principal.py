import argparse
import sys

from anotai.adapters.inbound.cli.comando_exibir import (
    configurar_parser_exibir,
    executar_comando_exibir,
)
from anotai.adapters.inbound.cli.comando_pdf import (
    configurar_parser_pdf,
    executar_comando_pdf,
)
from anotai.adapters.inbound.cli.comando_transcrever import (
    configurar_parser_transcrever,
    executar_comando_transcrever,
)
from anotai.adapters.inbound.cli.formatador_terminal import formatar_aula_texto
from anotai.adapters.outbound.persistence import RepositorioAulaSQLite
from anotai.application.use_cases import TranscreverAula
from anotai.config import Settings


def processar_pdf(args: argparse.Namespace, settings: Settings) -> int:
    return executar_comando_pdf(args, settings)


def transcrever_audio(args: argparse.Namespace, settings: Settings) -> int:
    return executar_comando_transcrever(
        args, settings, transcrever_cls=TranscreverAula, repo_cls=RepositorioAulaSQLite
    )


def exibir_aula(args: argparse.Namespace, settings: Settings) -> int:
    return executar_comando_exibir(args, settings, repo_cls=RepositorioAulaSQLite)


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anotai",
        description="AnotaAI — Alinhamento Temporal e Documental",
    )
    subparsers = parser.add_subparsers(dest="subcomando", help="Subcomandos disponíveis")

    configurar_parser_pdf(subparsers)
    configurar_parser_transcrever(subparsers)
    configurar_parser_exibir(subparsers)

    return parser


def main(argumentos: list[str] | None = None) -> int:
    settings = Settings.from_environment()
    parser = criar_parser()

    raw_args = sys.argv[1:] if argumentos is None else argumentos
    if raw_args and raw_args[0] not in ("pdf", "transcrever", "exibir", "-h", "--help"):
        if raw_args[0].lower().endswith(".pdf"):
            raw_args = ["pdf", *raw_args]
        elif any(
            raw_args[0].lower().endswith(ext)
            for ext in (".wav", ".mp3", ".m4a", ".mp4", ".mkv", ".webm")
        ):
            raw_args = ["transcrever", *raw_args]

    args = parser.parse_args(raw_args)

    if args.subcomando == "pdf":
        return processar_pdf(args, settings)
    if args.subcomando == "transcrever":
        return transcrever_audio(args, settings)
    if args.subcomando == "exibir":
        return exibir_aula(args, settings)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

__all__ = [
    "RepositorioAulaSQLite",
    "TranscreverAula",
    "criar_parser",
    "exibir_aula",
    "formatar_aula_texto",
    "main",
    "processar_pdf",
    "transcrever_audio",
]
