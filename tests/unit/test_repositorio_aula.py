from pathlib import Path

from anotai.adapters.outbound.persistence.repositorio_aula_sqlite import RepositorioAulaSQLite
from anotai.domain.entities import Aula, IntervaloExplicativo, SegmentoTranscricao
from anotai.domain.value_objects import IntervaloTempo, MetadadosAudio


def test_repositorio_aula_salvar_e_buscar(tmp_path: Path) -> None:
    caminho_banco = tmp_path / "teste_aula.sqlite"
    repo = RepositorioAulaSQLite(caminho_banco)

    metadados = MetadadosAudio(
        duracao=45.2,
        taxa_amostragem=16000,
        canais=1,
        formato="wav",
        codec="pcm_s16le",
    )

    seg1 = SegmentoTranscricao(
        id_segmento="seg-aula-1-0001",
        id_aula="aula-1",
        texto="Texto do primeiro segmento.",
        intervalo=IntervaloTempo(0.0, 5.0),
        ordem=1,
        confianca=0.9,
    )

    inter1 = IntervaloExplicativo(
        id_intervalo="interval-aula-1-0001",
        id_aula="aula-1",
        texto="Texto do primeiro segmento.",
        intervalo=IntervaloTempo(0.0, 5.0),
        ordem=1,
        ids_segmentos=["seg-aula-1-0001"],
    )

    aula = Aula(
        id_aula="aula-1",
        titulo="Aula de Teste",
        uri_origem=str(tmp_path / "audio.wav"),
        caminho_arquivo=tmp_path / "audio.wav",
        metadados=metadados,
        segmentos=[seg1],
        intervalos=[inter1],
        idioma="pt",
    )

    repo.salvar(aula, carga_bruta_asr={"raw_test": True})

    recuperada = repo.buscar_por_id("aula-1")
    assert recuperada is not None
    assert recuperada.id_aula == "aula-1"
    assert recuperada.titulo == "Aula de Teste"
    assert recuperada.metadados.duracao == 45.2
    assert recuperada.idioma == "pt"
    assert len(recuperada.segmentos) == 1
    assert recuperada.segmentos[0].id_segmento == "seg-aula-1-0001"
    assert recuperada.segmentos[0].texto == "Texto do primeiro segmento."
    assert len(recuperada.intervalos) == 1
    assert recuperada.intervalos[0].ids_segmentos == ["seg-aula-1-0001"]

    # Teste de listagem
    todas = repo.listar()
    assert len(todas) == 1
    assert todas[0].id_aula == "aula-1"

    # Buscar inexistente
    assert repo.buscar_por_id("inexistente") is None
