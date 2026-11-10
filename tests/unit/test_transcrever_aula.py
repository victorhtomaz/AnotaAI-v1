import json
from pathlib import Path

from anotai.application.ports.provedor_transcricao import ResultadoTranscricao, SegmentoBrutoASR
from anotai.application.use_cases.transcrever_aula import TranscreverAula
from anotai.domain.value_objects import MetadadosAudio


class InspetorFake:
    def inspecionar(self, caminho: Path) -> MetadadosAudio:
        return MetadadosAudio(duracao=30.0, taxa_amostragem=16000, canais=1, formato="wav")

    def extrair_wav_mono_16k(self, caminho_origem: Path, caminho_destino: Path) -> Path:
        caminho_destino.touch()
        return caminho_destino


class ProvedorTranscricaoFake:
    def __init__(self, segmentos: list[SegmentoBrutoASR], idioma: str = "pt") -> None:
        self.segmentos = segmentos
        self.idioma = idioma

    def transcrever(self, caminho_audio: Path) -> ResultadoTranscricao:
        return ResultadoTranscricao(
            idioma=self.idioma,
            segmentos=self.segmentos,
            carga_bruta={"raw": True, "test": 123},
        )


def test_transcrever_aula_fluxo_completo(tmp_path: Path) -> None:
    audio_path = tmp_path / "aula.wav"
    audio_path.write_bytes(b"dummy")

    diretorio_bruto = tmp_path / "brutos"

    segmentos_brutos = [
        SegmentoBrutoASR(texto="Primeira frase da aula.", inicio=0.0, fim=4.0, confianca=0.95),
        SegmentoBrutoASR(texto="Segunda frase da aula.", inicio=4.2, fim=10.5, confianca=0.92),
        SegmentoBrutoASR(texto="Terceira frase após pausa.", inicio=14.0, fim=18.0, confianca=0.88),
    ]

    inspetor = InspetorFake()
    provedor = ProvedorTranscricaoFake(segmentos_brutos)
    caso_uso = TranscreverAula(
        inspetor=inspetor,
        provedor=provedor,
        diretorio_bruto=diretorio_bruto,
    )

    aula = caso_uso.executar(audio_path, titulo="Minha Aula")

    assert aula.titulo == "Minha Aula"
    assert aula.idioma == "pt"
    assert len(aula.segmentos) == 3
    assert aula.segmentos[0].texto == "Primeira frase da aula."
    assert aula.segmentos[0].intervalo.inicio == 0.0
    assert aula.segmentos[0].intervalo.fim == 4.0

    # Intervalos explicativos agrupados
    assert len(aula.intervalos) == 2
    seg_ids_0 = [aula.segmentos[0].id_segmento, aula.segmentos[1].id_segmento]
    assert aula.intervalos[0].ids_segmentos == seg_ids_0
    assert aula.intervalos[1].ids_segmentos == [aula.segmentos[2].id_segmento]

    # Preservação da saída bruta do ASR
    arquivo_bruto = diretorio_bruto / f"{aula.id_aula}.json"
    assert arquivo_bruto.exists()
    dados_brutos = json.loads(arquivo_bruto.read_text(encoding="utf-8"))
    assert dados_brutos["id_aula"] == aula.id_aula
    assert dados_brutos["carga_bruta_asr"] == {"raw": True, "test": 123}


def test_transcrever_aula_corrige_anomalias_de_timestamp(tmp_path: Path) -> None:
    audio_path = tmp_path / "aula.wav"
    audio_path.write_bytes(b"dummy")

    # Segmento com início negativo e fim menor que início
    segmentos_brutos = [
        SegmentoBrutoASR(texto="Segmento anômalo", inicio=-0.5, fim=-0.5),
        SegmentoBrutoASR(texto="   ", inicio=2.0, fim=3.0),  # Vazio, deve ser ignorado
        SegmentoBrutoASR(texto="Segmento normal", inicio=3.0, fim=5.0),
    ]

    caso_uso = TranscreverAula(
        inspetor=InspetorFake(),
        provedor=ProvedorTranscricaoFake(segmentos_brutos),
    )
    aula = caso_uso.executar(audio_path)

    assert len(aula.segmentos) == 2
    # Início foi corrigido para >= 0.0 e fim ajustado para > início
    assert aula.segmentos[0].intervalo.inicio == 0.0
    assert aula.segmentos[0].intervalo.fim == 0.1
    assert aula.segmentos[1].texto == "Segmento normal"
