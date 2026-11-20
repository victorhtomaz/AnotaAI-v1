import argparse
import json
import sys
from pathlib import Path
from typing import Any

from anotai.adapters.inbound.cli.formatador_terminal import formatar_aula_texto
from anotai.application.use_cases import AgrupadorIntervalos, TranscreverAula
from anotai.bootstrap import (
    criar_inspetor_audio,
    criar_provedor_transcricao,
    obter_classes_repositorios,
)
from anotai.config import Settings
from anotai.domain.exceptions import ErroAudio, ErroIntegridade, ErroTranscricao


def configurar_parser_transcrever(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("transcrever", help="Transcreve uma aula em áudio/vídeo.")
    parser.add_argument("audio", type=Path, help="Caminho do áudio ou vídeo da aula.")
    parser.add_argument("--title", type=str, default=None, help="Título identificador da aula.")
    parser.add_argument(
        "--provider",
        choices=("whisperx", "azure_speech"),
        default=None,
        help="Provedor de transcrição (sobrescreve ANOTAI_PROVEDOR_TRANSCRICAO).",
    )
    parser.add_argument(
        "--language",
        type=str,
        default=None,
        help="Idioma da fala para provedor em nuvem (ex.: pt-BR).",
    )
    parser.add_argument("--model", type=str, default=None, help="Modelo WhisperX.")
    parser.add_argument("--device", type=str, default=None, help="Dispositivo (cpu/cuda).")
    parser.add_argument(
        "--compute-type",
        type=str,
        default=None,
        help="Tipo de computação (int8/float16).",
    )
    parser.add_argument(
        "--align-phonemes",
        action="store_true",
        help="Habilita alinhamento fonético refinado.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Formato de saída.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Exibe todos os segmentos atômicos de cada intervalo.",
    )


def executar_comando_transcrever(
    args: argparse.Namespace,
    settings: Settings,
    transcrever_cls: Any = TranscreverAula,
    repo_cls: Any = None,
) -> int:
    inspetor = criar_inspetor_audio()
    modelo = args.model or settings.whisperx_model
    dispositivo = args.device or settings.whisperx_device
    tipo_computacao = args.compute_type or settings.whisperx_compute_type
    alinhar = args.align_phonemes or settings.whisperx_align_phonemes

    _, padrao_aula_cls, _ = obter_classes_repositorios()
    repo_aula_cls = repo_cls or padrao_aula_cls
    repositorio = repo_aula_cls(Path(settings.database_path))
    agrupador = AgrupadorIntervalos(
        limiar_silencio=settings.interval_silence_threshold,
        duracao_minima=settings.interval_min_duration,
        duracao_maxima=settings.interval_max_duration,
    )
    diretorio_bruto = Path(settings.raw_transcripts_directory)

    try:
        provedor = criar_provedor_transcricao(
            modelo=modelo,
            dispositivo=dispositivo,
            tipo_computacao=tipo_computacao,
            alinhar_fonemas=alinhar,
            settings=settings,
            provedor=getattr(args, "provider", None),
            idioma=getattr(args, "language", None),
        )
        caso_uso = transcrever_cls(
            inspetor=inspetor,
            provedor=provedor,
            repositorio=repositorio,
            agrupador=agrupador,
            diretorio_bruto=diretorio_bruto,
        )
        aula = caso_uso.executar(args.audio, titulo=args.title)
    except (ErroAudio, ErroTranscricao, ErroIntegridade) as exc:
        print(f"Erro na transcrição de áudio: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        saida = {
            "id_aula": aula.id_aula,
            "titulo": aula.titulo,
            "duracao": aula.metadados.duracao,
            "idioma": aula.idioma,
            "quantidade_segmentos": len(aula.segmentos),
            "quantidade_intervalos": len(aula.intervalos),
            "intervalos": [
                {
                    "id": i.id_intervalo,
                    "ordem": i.ordem,
                    "inicio": i.intervalo.inicio,
                    "fim": i.intervalo.fim,
                    "duracao": i.intervalo.duracao,
                    "texto": i.texto,
                    "segmentos": i.ids_segmentos,
                }
                for i in aula.intervalos
            ],
        }
        print(json.dumps(saida, ensure_ascii=False, indent=2))
    else:
        print(formatar_aula_texto(aula, detalhado=args.verbose))

    return 0
