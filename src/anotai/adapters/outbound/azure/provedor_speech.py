from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from anotai.application.ports.provedor_transcricao import (
    ProvedorTranscricao,
    ResultadoTranscricao,
    SegmentoBrutoASR,
)
from anotai.domain.exceptions import ErroTranscricao

logger = logging.getLogger(__name__)

TICKS_POR_SEGUNDO = 10_000_000.0


class ProvedorAzureSpeech(ProvedorTranscricao):
    """Adaptador outbound de transcrição via Azure Speech SDK (reconhecimento contínuo)."""

    def __init__(
        self,
        chave: str,
        regiao: str = "",
        idioma: str = "pt-BR",
        endpoint: str = "",
        timestamps_palavras: bool = True,
        speech_sdk: Any = None,
    ) -> None:
        self.chave = chave
        self.regiao = regiao
        self.idioma = idioma or "pt-BR"
        self.endpoint = endpoint
        self.timestamps_palavras = timestamps_palavras
        self._speech_sdk = speech_sdk

    def _obter_sdk(self) -> Any:
        if self._speech_sdk is not None:
            return self._speech_sdk
        try:
            import azure.cognitiveservices.speech as speechsdk
        except ImportError as exc:
            raise ErroTranscricao(
                "SDK do Azure Speech não instalado. Execute: uv sync --extra azure"
            ) from exc
        return speechsdk

    def _sanitizar_mensagem(self, mensagem: str) -> str:
        if self.chave and self.chave in mensagem:
            return mensagem.replace(self.chave, "***")
        return mensagem

    def transcrever(self, caminho_audio: Path) -> ResultadoTranscricao:
        if not caminho_audio.exists():
            raise ErroTranscricao(
                f"arquivo de áudio não encontrado para transcrição: {caminho_audio}"
            )
        if not self.chave.strip() or not (self.regiao.strip() or self.endpoint.strip()):
            raise ErroTranscricao(
                "Credenciais do Azure Speech não configuradas: defina "
                "ANOTAI_AZURE_SPEECH_KEY e ANOTAI_AZURE_SPEECH_REGION (ou ENDPOINT)."
            )

        sdk = self._obter_sdk()
        try:
            if self.endpoint.strip():
                speech_config = sdk.SpeechConfig(
                    subscription=self.chave,
                    endpoint=self.endpoint.strip(),
                )
            else:
                speech_config = sdk.SpeechConfig(
                    subscription=self.chave,
                    region=self.regiao.strip(),
                )

            speech_config.speech_recognition_language = self.idioma
            speech_config.output_format = sdk.OutputFormat.Detailed
            if self.timestamps_palavras:
                speech_config.request_word_level_timestamps()

            audio_config = sdk.audio.AudioConfig(filename=str(caminho_audio))
            recognizer = sdk.SpeechRecognizer(
                speech_config=speech_config,
                audio_config=audio_config,
            )
        except Exception as exc:
            if isinstance(exc, ErroTranscricao):
                raise
            raise ErroTranscricao(
                "erro ao inicializar Azure Speech SDK: "
                f"{self._sanitizar_mensagem(str(exc))}"
            ) from exc

        evento_concluido = threading.Event()
        erros: list[str] = []
        segmentos: list[SegmentoBrutoASR] = []
        eventos_brutos: list[dict[str, Any]] = []

        def ao_reconhecer(evt: Any) -> None:
            resultado = getattr(evt, "result", None)
            if resultado is None:
                return
            if getattr(resultado, "reason", None) != sdk.ResultReason.RecognizedSpeech:
                return

            seg, payload_bruto = self._interpretar_resultado_reconhecido(resultado)
            if payload_bruto is not None:
                eventos_brutos.append(payload_bruto)
            if seg is not None:
                segmentos.append(seg)

        def ao_cancelar(evt: Any) -> None:
            resultado = getattr(evt, "result", None)
            detalhes = self._extrair_detalhes_cancelamento(sdk, evt, resultado)
            razao = getattr(detalhes, "reason", None)
            if razao == sdk.CancellationReason.Error:
                codigo = getattr(detalhes, "error_code", "")
                detalhe_erro = getattr(detalhes, "error_details", "") or "Erro desconhecido"
                texto_erro = self._sanitizar_mensagem(f"{codigo}: {detalhe_erro}".strip(": "))
                erros.append(texto_erro)
            evento_concluido.set()

        def ao_parar_sessao(_evt: Any) -> None:
            evento_concluido.set()

        recognizer.recognized.connect(ao_reconhecer)
        recognizer.canceled.connect(ao_cancelar)
        recognizer.session_stopped.connect(ao_parar_sessao)

        try:
            self._invocar_controle(recognizer, "start_continuous_recognition")
            evento_concluido.wait()
        except Exception as exc:
            if isinstance(exc, ErroTranscricao):
                raise
            raise ErroTranscricao(
                "erro ao executar transcrição via Azure Speech: "
                f"{self._sanitizar_mensagem(str(exc))}"
            ) from exc
        finally:
            try:
                self._invocar_controle(recognizer, "stop_continuous_recognition")
            except Exception as exc_stop:
                logger.warning(
                    "Falha ao encerrar sessão de reconhecimento do Azure Speech: %s",
                    self._sanitizar_mensagem(str(exc_stop)),
                )

        if erros:
            raise ErroTranscricao(f"Falha na transcrição via Azure Speech: {erros[0]}")

        return ResultadoTranscricao(
            idioma=self.idioma,
            segmentos=segmentos,
            carga_bruta={
                "provider": "azure_speech",
                "language": self.idioma,
                "region": self.regiao,
                "segments": eventos_brutos,
            },
        )

    @staticmethod
    def _invocar_controle(recognizer: Any, metodo_base: str) -> None:
        metodo_async = getattr(recognizer, f"{metodo_base}_async", None)
        if callable(metodo_async):
            futuro = metodo_async()
            if hasattr(futuro, "get") and callable(futuro.get):
                futuro.get()
            return
        metodo_sync = getattr(recognizer, metodo_base)
        metodo_sync()

    @staticmethod
    def _extrair_detalhes_cancelamento(sdk: Any, evt: Any, resultado: Any) -> Any:
        detalhes = getattr(evt, "cancellation_details", None) or getattr(
            resultado, "cancellation_details", None
        )
        if detalhes is not None:
            return detalhes
        fabrica = getattr(getattr(sdk, "CancellationDetails", None), "from_result", None)
        if callable(fabrica) and resultado is not None:
            return fabrica(resultado)
        if hasattr(sdk, "CancellationDetails") and resultado is not None:
            return sdk.CancellationDetails(resultado)
        return None

    @staticmethod
    def _interpretar_resultado_reconhecido(
        resultado: Any,
    ) -> tuple[SegmentoBrutoASR | None, dict[str, Any] | None]:
        json_bruto = getattr(resultado, "json", None)
        payload: dict[str, Any] | None = None
        if isinstance(json_bruto, str) and json_bruto.strip():
            try:
                decodificado = json.loads(json_bruto)
                if isinstance(decodificado, dict):
                    payload = decodificado
            except json.JSONDecodeError:
                payload = None

        texto = ""
        confianca: float | None = None
        palavras: list[dict[str, Any]] = []
        offset_ticks = float(getattr(resultado, "offset", 0) or 0)
        duration_ticks = float(getattr(resultado, "duration", 0) or 0)

        if payload is not None:
            nbest = payload.get("NBest")
            melhor = nbest[0] if isinstance(nbest, list) and nbest else {}
            if isinstance(melhor, dict):
                texto = str(
                    melhor.get("Display")
                    or melhor.get("Lexical")
                    or payload.get("DisplayText")
                    or getattr(resultado, "text", "")
                    or ""
                ).strip()
                conf_bruta = melhor.get("Confidence")
                if conf_bruta is not None:
                    confianca = round(float(conf_bruta), 4)

                palavras_raw = melhor.get("Words")
                if isinstance(palavras_raw, list):
                    for item in palavras_raw:
                        if not isinstance(item, dict):
                            continue
                        w_off = float(item.get("Offset", 0) or 0)
                        w_dur = float(item.get("Duration", 0) or 0)
                        w_txt = str(item.get("Word", "")).strip()
                        if not w_txt:
                            continue
                        palavra_dict: dict[str, Any] = {
                            "word": w_txt,
                            "start": round(w_off / TICKS_POR_SEGUNDO, 3),
                            "end": round((w_off + w_dur) / TICKS_POR_SEGUNDO, 3),
                        }
                        if item.get("Confidence") is not None:
                            palavra_dict["score"] = round(float(item["Confidence"]), 4)
                        palavras.append(palavra_dict)

            if payload.get("Offset") is not None:
                offset_ticks = float(payload["Offset"])
            if payload.get("Duration") is not None:
                duration_ticks = float(payload["Duration"])

        if not texto:
            texto = str(getattr(resultado, "text", "") or "").strip()

        if not texto:
            return None, payload

        inicio = round(max(0.0, offset_ticks / TICKS_POR_SEGUNDO), 3)
        fim = round(max(inicio, (offset_ticks + duration_ticks) / TICKS_POR_SEGUNDO), 3)
        if fim <= inicio and palavras:
            inicio = float(palavras[0]["start"])
            fim = float(palavras[-1]["end"])

        segmento = SegmentoBrutoASR(
            texto=texto,
            inicio=inicio,
            fim=fim,
            confianca=confianca,
            palavras=palavras,
        )
        return segmento, payload
