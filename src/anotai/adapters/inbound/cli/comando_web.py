import argparse
from typing import Any

import uvicorn

from anotai.adapters.inbound.web import criar_app
from anotai.config import Settings


def configurar_parser_web(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "web",
        help="Inicia a interface web para importação, processamento e inspeção.",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Endereço de escuta do servidor HTTP (padrão: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Porta TCP do servidor HTTP (padrão: 8000).",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Habilita recarregamento automático em desenvolvimento.",
    )


def executar_comando_web(
    args: argparse.Namespace,
    settings: Settings,
    app_factory: Any = criar_app,
    runner: Any = uvicorn.run,
) -> int:
    print(f"AnotaAI Web disponível em http://{args.host}:{args.port}")
    if getattr(args, "reload", False):
        runner(
            "anotai.adapters.inbound.web.app:criar_app",
            host=args.host,
            port=args.port,
            reload=True,
            factory=True,
        )
    else:
        app = app_factory(settings=settings)
        runner(app, host=args.host, port=args.port)
    return 0
