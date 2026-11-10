import hashlib
from pathlib import Path

from anotai.application.ports.inspetor_audio import InspetorAudio
from anotai.domain.entities.Aula import Aula
from anotai.domain.exceptions.AudioInvalido import AudioInvalido

EXTENSOES_SUPORTADAS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".aac",
    ".ogg",
    ".flac",
    ".wma",
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".webm",
}


class ImportarAudio:
    def __init__(self, inspetor: InspetorAudio) -> None:
        self._inspetor = inspetor

    def executar(self, caminho: Path, titulo: str | None = None) -> Aula:
        caminho_resolvido = caminho.resolve()
        if not caminho_resolvido.exists():
            raise AudioInvalido(f"arquivo de áudio não encontrado: {caminho}")
        if not caminho_resolvido.is_file():
            raise AudioInvalido(f"o caminho não é um arquivo: {caminho}")

        extensao = caminho_resolvido.suffix.lower()
        if extensao not in EXTENSOES_SUPORTADAS:
            suportadas_str = ", ".join(sorted(EXTENSOES_SUPORTADAS))
            raise AudioInvalido(
                f"extensão de arquivo não suportada: '{extensao}'. Suportadas: {suportadas_str}"
            )

        metadados = self._inspetor.inspecionar(caminho_resolvido)
        if metadados.duracao <= 0:
            raise AudioInvalido("o arquivo de áudio possui duração nula ou negativa")

        nome_base = caminho_resolvido.stem
        titulo_final = titulo or nome_base
        hash_id = hashlib.sha256(f"{nome_base}-{metadados.duracao}".encode()).hexdigest()[:12]
        id_aula = f"aula-{hash_id}"

        return Aula(
            id_aula=id_aula,
            titulo=titulo_final,
            uri_origem=str(caminho_resolvido),
            caminho_arquivo=caminho_resolvido,
            metadados=metadados,
        )
