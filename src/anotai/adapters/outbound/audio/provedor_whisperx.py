import logging
from pathlib import Path
from typing import Any

import torch
import whisperx

from anotai.application.ports.provedor_transcricao import (
    ProvedorTranscricao,
    ResultadoTranscricao,
    SegmentoBrutoASR,
)
from anotai.domain.exceptions import ErroTranscricao

logger = logging.getLogger(__name__)


class ProvedorWhisperX(ProvedorTranscricao):
    def __init__(
        self,
        modelo: str = "base",
        dispositivo: str = "auto",
        tipo_computacao: str = "auto",
        idioma: str | None = None,
        alinhar_fonemas: bool = False,
        tamanho_lote: int = 4,
    ) -> None:
        self.modelo = modelo
        self.dispositivo_solicitado = dispositivo
        self.tipo_computacao_solicitado = tipo_computacao
        self.idioma = idioma
        self.alinhar_fonemas = alinhar_fonemas
        self.tamanho_lote = tamanho_lote
        self._dispositivo, self._tipo_computacao = self._resolver_dispositivo_e_tipo(
            dispositivo, tipo_computacao
        )
        self._modelo_carregado: Any = None

    def _obter_modelo_asr(self) -> Any:
        if self._modelo_carregado is None:
            self._modelo_carregado = whisperx.load_model(
                self.modelo,
                device=self._dispositivo,
                compute_type=self._tipo_computacao,
                language=self.idioma,
            )
        return self._modelo_carregado

    @staticmethod
    def _resolver_dispositivo_e_tipo(dispositivo: str, tipo_computacao: str) -> tuple[str, str]:
        dispositivo_resolvido = dispositivo
        if dispositivo_resolvido in ("auto", None):
            dispositivo_resolvido = "cuda" if torch.cuda.is_available() else "cpu"

        tipo_resolvido = tipo_computacao
        if tipo_resolvido in ("auto", None):
            tipo_resolvido = "float16" if dispositivo_resolvido == "cuda" else "int8"
        elif dispositivo_resolvido == "cpu" and tipo_resolvido == "float16":
            # ctranslate2 não suporta float16 em CPU
            tipo_resolvido = "int8"

        return dispositivo_resolvido, tipo_resolvido

    def transcrever(self, caminho_audio: Path) -> ResultadoTranscricao:
        if not caminho_audio.exists():
            raise ErroTranscricao(
                f"arquivo de áudio não encontrado para transcrição: {caminho_audio}"
            )

        try:
            modelo_asr = self._obter_modelo_asr()
            audio = whisperx.load_audio(str(caminho_audio))
            resultado_bruto = modelo_asr.transcribe(audio, batch_size=self.tamanho_lote)

            idioma_detectado = resultado_bruto.get("language", self.idioma or "pt")

            if self.alinhar_fonemas and resultado_bruto.get("segments"):
                try:
                    modelo_alinhamento, metadados = whisperx.load_align_model(
                        language_code=idioma_detectado,
                        device=self._dispositivo,
                    )
                    resultado_bruto = whisperx.align(
                        resultado_bruto["segments"],
                        modelo_alinhamento,
                        metadados,
                        audio,
                        self._dispositivo,
                        return_char_alignments=False,
                    )
                except Exception as exc:
                    logger.warning(
                        "Alinhamento fonético opcional não concluído, preservando timestamps: %s",
                        exc,
                    )

            segmentos: list[SegmentoBrutoASR] = []
            for seg in resultado_bruto.get("segments", []):
                texto = seg.get("text", "").strip()
                if not texto:
                    continue

                inicio = float(seg.get("start", 0.0))
                fim = float(seg.get("end", 0.0))
                confianca = seg.get("score")
                palavras: list[dict[str, Any]] = seg.get("words", [])

                segmentos.append(
                    SegmentoBrutoASR(
                        texto=texto,
                        inicio=inicio,
                        fim=fim,
                        confianca=float(confianca) if confianca is not None else None,
                        palavras=palavras,
                    )
                )

            return ResultadoTranscricao(
                idioma=idioma_detectado,
                segmentos=segmentos,
                carga_bruta=resultado_bruto,
            )

        except Exception as exc:
            if isinstance(exc, ErroTranscricao):
                raise
            raise ErroTranscricao(f"erro ao executar transcrição via WhisperX: {exc}") from exc
