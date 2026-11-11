import argparse
import sys

from anotai.adapters.inbound.cli.comando_alinhar import (
    configurar_parser_alinhar,
    executar_comando_alinhar,
)
from anotai.adapters.inbound.cli.comando_buscar import (
    configurar_parser_buscar,
    executar_comando_buscar,
)
from anotai.adapters.inbound.cli.comando_exibir import (
    configurar_parser_exibir,
    executar_comando_exibir,
)
from anotai.adapters.inbound.cli.comando_listar import (
    configurar_parser_listar,
    executar_comando_listar,
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


def buscar_candidatos(args: argparse.Namespace, settings: Settings) -> int:
    return executar_comando_buscar(args, settings)


def alinhar_aula(args: argparse.Namespace, settings: Settings) -> int:
    return executar_comando_alinhar(args, settings)


def listar_itens(args: argparse.Namespace, settings: Settings) -> int:
    return executar_comando_listar(args, settings)


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anotai",
        description="AnotaAI — Alinhamento Temporal e Documental",
    )
    subparsers = parser.add_subparsers(dest="subcomando", help="Subcomandos disponíveis")

    configurar_parser_pdf(subparsers)
    configurar_parser_transcrever(subparsers)
    configurar_parser_exibir(subparsers)
    configurar_parser_buscar(subparsers)
    configurar_parser_alinhar(subparsers)
    configurar_parser_listar(subparsers)

    return parser


def main(argumentos: list[str] | None = None) -> int:
    settings = Settings.from_environment()
    parser = criar_parser()

    raw_args = sys.argv[1:] if argumentos is None else argumentos
    exts_audio = (".wav", ".mp3", ".m4a", ".mp4", ".mkv", ".webm")

    if raw_args and raw_args[0] not in (
        "pdf",
        "transcrever",
        "exibir",
        "buscar",
        "alinhar",
        "listar",
        "-h",
        "--help",
    ):
        # Atalho com 2 arquivos (áudio + pdf ou pdf + áudio) -> aciona alinhar diretamente
        if len(raw_args) >= 2:
            arg1, arg2 = raw_args[0].lower(), raw_args[1].lower()
            eh_audio_1 = any(arg1.endswith(e) for e in exts_audio)
            eh_pdf_1 = arg1.endswith(".pdf")
            eh_audio_2 = any(arg2.endswith(e) for e in exts_audio)
            eh_pdf_2 = arg2.endswith(".pdf")
            if (eh_audio_1 and eh_pdf_2) or (eh_pdf_1 and eh_audio_2):
                raw_args = ["alinhar", *raw_args]
        # Atalho com 1 arquivo
        if raw_args[0] not in ("alinhar", "pdf", "transcrever"):
            if raw_args[0].lower().endswith(".pdf"):
                raw_args = ["pdf", *raw_args]
            elif any(raw_args[0].lower().endswith(ext) for ext in exts_audio):
                raw_args = ["transcrever", *raw_args]

    args = parser.parse_args(raw_args)

    if args.subcomando == "pdf":
        return processar_pdf(args, settings)
    if args.subcomando == "transcrever":
        return transcrever_audio(args, settings)
    if args.subcomando == "exibir":
        return exibir_aula(args, settings)
    if args.subcomando == "buscar":
        return buscar_candidatos(args, settings)
    if args.subcomando == "alinhar":
        return alinhar_aula(args, settings)
    if args.subcomando == "listar":
        return listar_itens(args, settings)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

__all__ = [
    "RepositorioAulaSQLite",
    "TranscreverAula",
    "alinhar_aula",
    "buscar_candidatos",
    "criar_parser",
    "exibir_aula",
    "formatar_aula_texto",
    "listar_itens",
    "main",
    "processar_pdf",
    "transcrever_audio",
]
