import argparse
import json
from pathlib import Path

from ollama import Client

from anotai.adapters.outbound.ollama import AnalisadorVisualOllama
from anotai.adapters.outbound.pdf import ExtratorPDF
from anotai.adapters.outbound.persistence import ArmazenamentoDocumento
from anotai.application.use_cases import ImportarDocumento
from anotai.config import Settings
from anotai.domain.exceptions.ErroProcessamentoDocumento import ErroProcessamentoDocumento


def main() -> int:
    parser = argparse.ArgumentParser(description="Processa um PDF do AnotaAI.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument(
        "--method",
        choices=("native", "native_then_ocr"),
        default="native_then_ocr",
    )
    args = parser.parse_args()
    settings = Settings.from_environment()
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
        parser.error(str(exc))
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


if __name__ == "__main__":
    raise SystemExit(main())
