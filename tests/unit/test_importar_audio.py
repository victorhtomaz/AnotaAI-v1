from pathlib import Path

import pytest

from anotai.application.use_cases.importar_audio import ImportarAudio
from anotai.domain.exceptions.AudioInvalido import AudioInvalido
from anotai.domain.value_objects.MetadadosAudio import MetadadosAudio


class InspetorAudioFake:
    def __init__(self, duracao: float = 60.0, taxa: int = 44100, canais: int = 2) -> None:
        self.duracao = duracao
        self.taxa = taxa
        self.canais = canais

    def inspecionar(self, caminho: Path) -> MetadadosAudio:
        return MetadadosAudio(
            duracao=self.duracao,
            taxa_amostragem=self.taxa,
            canais=self.canais,
            formato=caminho.suffix.lstrip("."),
        )

    def extrair_wav_mono_16k(self, caminho_origem: Path, caminho_destino: Path) -> Path:
        caminho_destino.touch()
        return caminho_destino


def test_importar_audio_sucesso(tmp_path: Path) -> None:
    arquivo_audio = tmp_path / "aula_01.mp3"
    arquivo_audio.write_bytes(b"dummy audio content")

    inspetor = InspetorAudioFake(duracao=120.5)
    caso_uso = ImportarAudio(inspetor)
    aula = caso_uso.executar(arquivo_audio, titulo="Aula 01 - Introdução")

    assert aula.titulo == "Aula 01 - Introdução"
    assert aula.caminho_arquivo == arquivo_audio.resolve()
    assert aula.metadados.duracao == 120.5
    assert aula.id_aula.startswith("aula-")


def test_importar_audio_sucesso_mkv(tmp_path: Path) -> None:
    arquivo_mkv = tmp_path / "aula_gravada.mkv"
    arquivo_mkv.write_bytes(b"dummy mkv content")

    inspetor = InspetorAudioFake(duracao=3600.0)
    caso_uso = ImportarAudio(inspetor)
    aula = caso_uso.executar(arquivo_mkv)

    assert aula.titulo == "aula_gravada"
    assert aula.caminho_arquivo == arquivo_mkv.resolve()
    assert aula.metadados.duracao == 3600.0
    assert aula.id_aula.startswith("aula-")


def test_importar_audio_arquivo_inexistente(tmp_path: Path) -> None:
    arquivo_inexistente = tmp_path / "nao_existe.wav"
    inspetor = InspetorAudioFake()
    caso_uso = ImportarAudio(inspetor)

    with pytest.raises(AudioInvalido, match="arquivo de áudio não encontrado"):
        caso_uso.executar(arquivo_inexistente)


def test_importar_audio_formato_nao_suportado(tmp_path: Path) -> None:
    arquivo_txt = tmp_path / "arquivo.txt"
    arquivo_txt.write_text("texto")

    inspetor = InspetorAudioFake()
    caso_uso = ImportarAudio(inspetor)

    with pytest.raises(AudioInvalido, match="extensão de arquivo não suportada"):
        caso_uso.executar(arquivo_txt)


def test_importar_audio_duracao_invalida(tmp_path: Path) -> None:
    arquivo_audio = tmp_path / "vazio.mp3"
    arquivo_audio.write_bytes(b"dummy")

    inspetor = InspetorAudioFake(duracao=0.0)
    with pytest.raises(ValueError, match="duração do áudio deve ser positiva"):
        ImportarAudio(inspetor).executar(arquivo_audio)
