import argparse
import json
import sys
from pathlib import Path
from typing import Any

from anotai.application.use_cases import ImportarDocumento
from anotai.bootstrap import (
    criar_analisador_visual,
    criar_extrator_documento,
    obter_classes_repositorios,
)
from anotai.config import Settings
from anotai.domain.exceptions import ErroIntegridade, ErroProcessamentoDocumento


def configurar_parser_pdf(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("pdf", help="Processa um PDF do material didático.")
    parser.add_argument("pdf", type=Path, help="Caminho do arquivo PDF.")
    parser.add_argument(
        "--method",
        choices=("native", "native_then_ocr"),
        default="native_then_ocr",
        help="Método de extração textual.",
    )
    parser.add_argument(
        "--visual-provider",
        choices=("ollama", "google_ai_studio"),
        default=None,
        help="Provedor de análise visual/OCR (sobrescreve ANOTAI_PROVEDOR_VISUAL).",
    )


def executar_comando_pdf(
    args: argparse.Namespace,
    settings: Settings,
    repo_cls: Any = None,
    importar_cls: Any = ImportarDocumento,
    extrator_cls: Any = None,
) -> int:
    padrao_doc_cls, _, _ = obter_classes_repositorios()
    repo_doc_cls = repo_cls or padrao_doc_cls
    banco_path = Path(settings.database_path)
    repositorio = repo_doc_cls(banco_path)

    try:
        analisador = None
        if args.method == "native_then_ocr":
            visual_provider = getattr(args, "visual_provider", None)
            analisador = criar_analisador_visual(
                settings,
                settings.visual_model,
                temperatura=settings.visual_temperature,
                seed=settings.visual_seed,
                pensar=settings.visual_think,
                provedor=visual_provider,
            )

        extrator = criar_extrator_documento(analisador, extrator_cls=extrator_cls)
        caso_uso = importar_cls(extrator, repositorio=repositorio)
        documento = caso_uso.executar(args.pdf, args.method)
    except (ErroProcessamentoDocumento, ErroIntegridade) as exc:
        print(f"Erro ao processar PDF: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "document_id": documento.id_documento,
                "pages": len(documento.paginas),
                "units": sum(len(pagina.unidades) for pagina in documento.paginas),
                "processing_version": documento.versao_processamento,
                "processed_path": str(banco_path),
            },
            ensure_ascii=False,
        )
    )
    return 0
