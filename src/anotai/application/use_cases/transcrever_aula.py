import json
import logging
import tempfile
from pathlib import Path

from anotai.application.ports.inspetor_audio import InspetorAudio
from anotai.application.ports.provedor_transcricao import ProvedorTranscricao
from anotai.application.ports.repositorio_aula import RepositorioAula
from anotai.application.use_cases.agrupar_intervalos import AgrupadorIntervalos
from anotai.application.use_cases.importar_audio import ImportarAudio
from anotai.domain.entities import Aula, SegmentoTranscricao
from anotai.domain.value_objects import IntervaloTempo

logger = logging.getLogger(__name__)


class TranscreverAula:
    def __init__(
        self,
        inspetor: InspetorAudio,
        provedor: ProvedorTranscricao,
        repositorio: RepositorioAula | None = None,
        agrupador: AgrupadorIntervalos | None = None,
        diretorio_bruto: Path | None = None,
    ) -> None:
        self._inspetor = inspetor
        self._provedor = provedor
        self._repositorio = repositorio
        self._agrupador = agrupador or AgrupadorIntervalos()
        self._diretorio_bruto = diretorio_bruto

    def executar(self, caminho_arquivo: Path, titulo: str | None = None) -> Aula:
        importador = ImportarAudio(self._inspetor)
        aula = importador.executar(caminho_arquivo, titulo=titulo)

        # Prepara arquivo WAV temporário normalizado (16kHz mono)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_wav = Path(temp_file.name)

        try:
            self._inspetor.extrair_wav_mono_16k(aula.caminho_arquivo, temp_wav)
            resultado = self._provedor.transcrever(temp_wav)
        finally:
            if temp_wav.exists():
                try:
                    temp_wav.unlink()
                except OSError:
                    logger.warning("Falha ao remover arquivo WAV temporário: %s", temp_wav)

        segmentos: list[SegmentoTranscricao] = []
        ordem = 1

        for raw_seg in resultado.segmentos:
            texto = raw_seg.texto.strip()
            if not texto:
                continue

            inicio = max(0.0, float(raw_seg.inicio))
            fim = float(raw_seg.fim)

            if fim <= inicio:
                # Trata anomalia de timestamp garantindo duração mínima positiva
                fim = inicio + 0.1

            intervalo = IntervaloTempo(round(inicio, 3), round(fim, 3))
            id_segmento = f"segment-{aula.id_aula}-{ordem:04d}"

            segmento = SegmentoTranscricao(
                id_segmento=id_segmento,
                id_aula=aula.id_aula,
                texto=texto,
                intervalo=intervalo,
                ordem=ordem,
                fonte="asr",
                confianca=raw_seg.confianca,
                palavras=raw_seg.palavras or [],
            )
            segmentos.append(segmento)
            ordem += 1

        intervalos = self._agrupador.agrupar(segmentos, aula.id_aula)

        aula.segmentos = segmentos
        aula.intervalos = intervalos
        aula.idioma = resultado.idioma

        # Preservação da saída bruta do ASR para auditoria
        if self._diretorio_bruto:
            self._salvar_carga_bruta(aula, resultado.carga_bruta)

        if self._repositorio:
            self._repositorio.salvar(aula, carga_bruta_asr=resultado.carga_bruta)

        return aula

    def _salvar_carga_bruta(self, aula: Aula, carga_bruta: dict) -> Path:
        assert self._diretorio_bruto is not None
        self._diretorio_bruto.mkdir(parents=True, exist_ok=True)
        destino = self._diretorio_bruto / f"{aula.id_aula}.json"
        conteudo = {
            "id_aula": aula.id_aula,
            "titulo": aula.titulo,
            "uri_origem": aula.uri_origem,
            "idioma": aula.idioma,
            "duracao_audio": aula.metadados.duracao,
            "quantidade_segmentos": len(aula.segmentos),
            "quantidade_intervalos": len(aula.intervalos),
            "carga_bruta_asr": carga_bruta,
        }
        with destino.open("w", encoding="utf-8") as f:
            json.dump(conteudo, f, ensure_ascii=False, indent=2)
        return destino
