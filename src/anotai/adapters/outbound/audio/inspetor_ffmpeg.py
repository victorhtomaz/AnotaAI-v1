import json
import logging
import subprocess
from pathlib import Path

from anotai.application.ports.inspetor_audio import InspetorAudio
from anotai.domain.exceptions import AudioInvalido
from anotai.domain.value_objects import MetadadosAudio

logger = logging.getLogger(__name__)


class InspetorFFmpeg(InspetorAudio):
    def __init__(
        self,
        executavel_ffprobe: str = "ffprobe",
        executavel_ffmpeg: str = "ffmpeg",
    ) -> None:
        self._ffprobe = executavel_ffprobe
        self._ffmpeg = executavel_ffmpeg

    @staticmethod
    def _converter_duracao_para_segundos(duracao_str: str) -> float:
        duracao_str = duracao_str.strip()
        if ":" in duracao_str:
            partes = duracao_str.split(":")
            if len(partes) == 3:
                h, m, s = partes
                return float(h) * 3600.0 + float(m) * 60.0 + float(s)
            if len(partes) == 2:
                m, s = partes
                return float(m) * 60.0 + float(s)
        return float(duracao_str)

    def inspecionar(self, caminho: Path) -> MetadadosAudio:
        if not caminho.exists():
            raise AudioInvalido(f"arquivo de áudio não encontrado: {caminho}")

        show_entries = (
            "stream=codec_name,sample_rate,channels,duration,tags:"
            "format=duration,format_name,bit_rate,tags"
        )
        cmd = [
            self._ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            show_entries,
            "-of",
            "json",
            str(caminho),
        ]

        try:
            resultado = subprocess.run(cmd, capture_output=True, text=True, check=True)
            dados = json.loads(resultado.stdout)
        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError) as exc:
            detalhe = getattr(exc, "stderr", "") or ""
            msg = f"falha ao inspecionar áudio com ffprobe: {exc}"
            if detalhe:
                msg += f" ({detalhe.strip()})"
            raise AudioInvalido(msg) from exc

        formato_info = dados.get("format", {})
        streams = dados.get("streams", [])

        if not streams:
            raise AudioInvalido("nenhum stream de áudio detectado no arquivo")

        primeiro_stream = streams[0]
        formato_tags = formato_info.get("tags") or {}
        stream_tags = primeiro_stream.get("tags") or {}

        duracao_str = (
            formato_info.get("duration")
            or primeiro_stream.get("duration")
            or formato_tags.get("DURATION")
            or formato_tags.get("DURATION-eng")
            or stream_tags.get("DURATION")
            or stream_tags.get("DURATION-eng")
        )

        if not duracao_str:
            raise AudioInvalido("não foi possível determinar a duração do arquivo de áudio")

        try:
            duracao = self._converter_duracao_para_segundos(str(duracao_str))
        except ValueError as exc:
            raise AudioInvalido(f"duração inválida retornada pelo ffprobe: {duracao_str}") from exc

        taxa_str = primeiro_stream.get("sample_rate", "16000")
        canais_int = int(primeiro_stream.get("channels", 1))
        codec = primeiro_stream.get("codec_name")
        formato = formato_info.get("format_name", caminho.suffix.lstrip("."))
        taxa_bits_str = formato_info.get("bit_rate")
        taxa_bits = int(taxa_bits_str) if taxa_bits_str and taxa_bits_str.isdigit() else None

        return MetadadosAudio(
            duracao=round(duracao, 3),
            taxa_amostragem=int(taxa_str),
            canais=canais_int,
            formato=formato,
            codec=codec,
            taxa_bits=taxa_bits,
        )

    def extrair_wav_mono_16k(self, caminho_origem: Path, caminho_destino: Path) -> Path:
        if not caminho_origem.exists():
            raise AudioInvalido(f"arquivo de origem não encontrado: {caminho_origem}")

        caminho_destino.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self._ffmpeg,
            "-y",
            "-i",
            str(caminho_origem),
            "-vn",
            "-sn",
            "-dn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(caminho_destino),
        ]

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            detalhe = getattr(exc, "stderr", "") or ""
            msg = f"falha ao converter áudio com ffmpeg: {exc}"
            if detalhe:
                msg += f" ({detalhe.strip()})"
            raise AudioInvalido(msg) from exc

        return caminho_destino
