from __future__ import annotations

import mimetypes
import re
from collections.abc import Iterator
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse

TAMANHO_CHUNK_STREAM = 64 * 1024
PADRAO_RANGE_BYTES = re.compile(r"^bytes=(\d*)-(\d*)$")

EXTENSOES_MIME_AUDIO = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".mkv": "video/x-matroska",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
}


def parse_range_header(range_header: str, tamanho_total: int) -> tuple[int, int] | None:
    """Interpreta o cabeçalho HTTP Range (`bytes=inicio-fim`) retornando os limites inclusivos."""
    correspondencia = PADRAO_RANGE_BYTES.match(range_header.strip())
    if not correspondencia:
        return None
    inicio_txt, fim_txt = correspondencia.groups()
    if not inicio_txt and not fim_txt:
        return None

    if not inicio_txt:
        sufixo = int(fim_txt)
        if sufixo <= 0:
            return None
        inicio = max(0, tamanho_total - sufixo)
        fim = tamanho_total - 1
    else:
        inicio = int(inicio_txt)
        fim = int(fim_txt) if fim_txt else tamanho_total - 1

    if inicio >= tamanho_total or fim < inicio:
        return None
    fim = min(fim, tamanho_total - 1)
    return inicio, fim


def iterar_arquivo_intervalo(caminho: Path, inicio: int, fim: int) -> Iterator[bytes]:
    """Lê um intervalo de bytes do arquivo em blocos para StreamingResponse em threadpool."""
    restante = fim - inicio + 1
    with caminho.open("rb") as arquivo:
        arquivo.seek(inicio)
        while restante > 0:
            bloco = arquivo.read(min(TAMANHO_CHUNK_STREAM, restante))
            if not bloco:
                break
            restante -= len(bloco)
            yield bloco


def servir_audio_com_range(caminho_audio: Path, range_header: str | None) -> Response:
    """Serve o arquivo de áudio com suporte completo a HTTP 206 Partial Content."""
    if not caminho_audio.is_file():
        raise HTTPException(
            status_code=404,
            detail="Arquivo de áudio não encontrado no disco.",
        )

    tamanho_total = caminho_audio.stat().st_size
    ext = caminho_audio.suffix.lower()
    media_type = (
        EXTENSOES_MIME_AUDIO.get(ext)
        or mimetypes.guess_type(caminho_audio.name)[0]
        or "application/octet-stream"
    )

    if not range_header:
        return StreamingResponse(
            iterar_arquivo_intervalo(caminho_audio, 0, max(0, tamanho_total - 1)),
            status_code=200,
            media_type=media_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(tamanho_total),
            },
        )

    intervalo = parse_range_header(range_header, tamanho_total)
    if intervalo is None:
        return Response(
            status_code=416,
            headers={"Content-Range": f"bytes */{tamanho_total}", "Accept-Ranges": "bytes"},
        )

    inicio, fim = intervalo
    tamanho_conteudo = fim - inicio + 1
    return StreamingResponse(
        iterar_arquivo_intervalo(caminho_audio, inicio, fim),
        status_code=206,
        media_type=media_type,
        headers={
            "Content-Range": f"bytes {inicio}-{fim}/{tamanho_total}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(tamanho_conteudo),
        },
    )
