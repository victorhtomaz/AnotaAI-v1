import argparse
import json
import sys
from pathlib import Path

from ollama import Client

from anotai.adapters.outbound.ollama import AnalisadorVisualOllama
from anotai.adapters.outbound.pdf import ExtratorPDF
from anotai.adapters.outbound.persistence import ArmazenamentoDocumento
from anotai.application.use_cases import ImportarDocumento
from anotai.config import Settings
from anotai.domain.exceptions.ErroProcessamentoDocumento import ErroProcessamentoDocumento


def configurar_parser_pdf(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("pdf", help="Processa um PDF do material didático.")
    parser.add_argument("pdf", type=Path, help="Caminho do arquivo PDF.")
    parser.add_argument(
        "--method",
        choices=("native", "native_then_ocr"),
        default="native_then_ocr",
        help="Método de extração textual.",
    )


def executar_comando_pdf(args: argparse.Namespace, settings: Settings) -> int:
    analisador = None
    if args.method == "native_then_ocr":
        analisador = AnalisadorVisualOllama(
            Client(host=settings.ollama_url),
            settings.visual_model,
            temperatura=settings.visual_temperature,
            seed=settings.visual_seed,
            pensar=settings.visual_think,
            manter_vivo=settings.ollama_keep_alive,
        )
    try:
        documento = ImportarDocumento(ExtratorPDF(analisador)).executar(args.pdf, args.method)
        destino = ArmazenamentoDocumento(Path(settings.database_path)).salvar(documento)
    except ErroProcessamentoDocumento as exc:
        print(f"Erro ao processar PDF: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "document_id": documento.id_documento,
                "pages": len(documento.paginas),
                "units": sum(len(pagina.unidades) for pagina in documento.paginas),
                "processing_version": documento.versao_processamento,
                "processed_path": str(destino),
            },
            ensure_ascii=False,
        )
    )
    return 0
