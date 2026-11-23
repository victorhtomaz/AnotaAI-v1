from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from anotai.adapters.outbound.google.analisador_visual import (
    CODIGOS_HTTP_TRANSITORIOS,
    MARCADORES_ERRO_TRANSITORIO,
)
from anotai.domain.exceptions import ErroBusca

logger = logging.getLogger(__name__)

MODELO_PADRAO_GOOGLE_EMBEDDING = "gemini-embedding-001"


@dataclass
class ProvedorEmbeddingGoogleAIStudio:
    """Adaptador outbound de embeddings usando o SDK oficial google-genai."""

    chave: str = ""
    modelo: str = MODELO_PADRAO_GOOGLE_EMBEDDING
    dimensoes_saida: int | None = None
    tipo_tarefa: str | None = None
    timeout_segundos: float = 60.0
    tamanho_lote: int = 100
    max_tentativas: int = 3
    backoff_inicial_segundos: float = 2.0
    intervalo_entre_requisicoes_segundos: float = 0.5
    max_concorrencia: int = 2
    cliente: Any = None
    genai_sdk: Any = None
    sleep_fn: Callable[[float], None] = time.sleep
    clock_fn: Callable[[], float] = time.monotonic
    _cache: dict[str, list[float]] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _ultimo_envio: float | None = field(default=None, init=False, repr=False, compare=False)
    _lock_pacing: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False, compare=False
    )
    _semaforo: threading.Semaphore = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._semaforo = threading.Semaphore(max(1, int(self.max_concorrencia)))

    def validar_configuracao(self) -> None:
        if self.cliente is None and not self.chave.strip():
            raise ErroBusca(
                "Chave do Google AI Studio não configurada: defina "
                "ANOTAI_GOOGLE_API_KEY (ou GEMINI_API_KEY)."
            )

    def _obter_modulos_sdk(self) -> tuple[Any, Any]:
        if self.genai_sdk is not None:
            return self.genai_sdk, getattr(self.genai_sdk, "types", None)
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ErroBusca(
                "SDK do Google GenAI não instalado. Execute: uv sync --extra google"
            ) from exc
        return genai, types

    def _obter_cliente(self) -> tuple[Any, Any]:
        if self.cliente is not None:
            types_mod = getattr(self.genai_sdk, "types", None)
            if types_mod is None:
                try:
                    from google.genai import types as types_mod
                except ImportError:
                    types_mod = None
            return self.cliente, types_mod

        genai, types = self._obter_modulos_sdk()
        http_options = self._construir_http_options(types)
        kwargs: dict[str, Any] = {"api_key": self.chave.strip()}
        if http_options is not None:
            kwargs["http_options"] = http_options
        self.cliente = genai.Client(**kwargs)
        return self.cliente, types

    def _construir_http_options(self, types: Any) -> Any:
        if types is None or not hasattr(types, "HttpOptions"):
            return None
        return types.HttpOptions(timeout=max(1000, int(self.timeout_segundos * 1000)))

    def _construir_config(self, types: Any) -> Any:
        kwargs: dict[str, Any] = {}
        if self.dimensoes_saida is not None:
            kwargs["output_dimensionality"] = int(self.dimensoes_saida)
        if self.tipo_tarefa:
            kwargs["task_type"] = self.tipo_tarefa
        if not kwargs:
            return None
        if types is not None and hasattr(types, "EmbedContentConfig"):
            return types.EmbedContentConfig(**kwargs)
        return kwargs

    def gerar_embeddings(self, textos: Sequence[str]) -> list[list[float]]:
        if not textos:
            return []

        lista_textos = [str(t) for t in textos]
        faltantes_unicos = list(dict.fromkeys(t for t in lista_textos if t not in self._cache))
        nao_vazios = [t for t in faltantes_unicos if t.strip()]

        if nao_vazios:
            self.validar_configuracao()
            cliente, types = self._obter_cliente()
            config = self._construir_config(types)
            lote_efetivo = max(1, int(self.tamanho_lote))

            for i in range(0, len(nao_vazios), lote_efetivo):
                chunk = nao_vazios[i : i + lote_efetivo]
                novos_vetores = self._gerar_lote(cliente=cliente, textos=chunk, config=config)
                for texto, vetor in zip(chunk, novos_vetores, strict=True):
                    self._cache[texto] = vetor

        vazios = [t for t in faltantes_unicos if not t.strip()]
        if vazios:
            dimensao = self._descobrir_dimensao_cache()
            vetor_nulo = [0.0] * dimensao
            for texto in vazios:
                self._cache[texto] = list(vetor_nulo)

        return [self._cache[t] for t in lista_textos]

    def _descobrir_dimensao_cache(self) -> int:
        for vetor in self._cache.values():
            if vetor:
                return len(vetor)
        if self.dimensoes_saida is not None and self.dimensoes_saida > 0:
            return int(self.dimensoes_saida)
        return 1

    def _gerar_lote(
        self,
        *,
        cliente: Any,
        textos: list[str],
        config: Any,
    ) -> list[list[float]]:
        modelo_efetivo = self.modelo.strip() or MODELO_PADRAO_GOOGLE_EMBEDDING
        tentativas = max(1, int(self.max_tentativas))

        for tentativa in range(tentativas):
            try:
                kwargs: dict[str, Any] = {
                    "model": modelo_efetivo,
                    "contents": textos,
                }
                if config is not None:
                    kwargs["config"] = config

                with self._semaforo:
                    self._aguardar_pacing()
                    resposta = cliente.models.embed_content(**kwargs)

                return self._extrair_vetores(resposta, len(textos), modelo_efetivo)
            except ErroBusca:
                raise
            except Exception as exc:
                categoria, status = self._classificar_erro(exc)
                resumo = self._sanitizar_mensagem(str(exc).strip() or exc.__class__.__name__)

                if categoria == "auth":
                    rotulo_status = status if isinstance(status, int) else "401/403"
                    raise ErroBusca(
                        "Falha de autenticação/autorização no Google AI Studio "
                        f"ao gerar embeddings (HTTP {rotulo_status})"
                    ) from exc

                if categoria == "transient" and tentativa < tentativas - 1:
                    atraso = self._calcular_backoff(tentativa)
                    logger.warning(
                        "Erro transitório no Google AI Studio ao gerar embeddings (%s, "
                        "tentativa %s/%s); aguardando %.1fs: %s",
                        modelo_efetivo,
                        tentativa + 1,
                        tentativas,
                        atraso,
                        resumo,
                    )
                    if atraso > 0.0:
                        self.sleep_fn(atraso)
                    continue

                raise ErroBusca(
                    f"Falha ao gerar embeddings via Google AI Studio com modelo "
                    f"'{modelo_efetivo}': {resumo}"
                ) from exc

        raise ErroBusca(
            f"Falha ao gerar embeddings via Google AI Studio com modelo '{modelo_efetivo}'"
        )

    @staticmethod
    def _extrair_vetores(
        resposta: Any,
        quantidade_esperada: int,
        modelo: str,
    ) -> list[list[float]]:
        embeddings = (
            resposta.get("embeddings")
            if isinstance(resposta, dict)
            else getattr(resposta, "embeddings", None)
        )
        if not embeddings:
            raise ErroBusca(
                f"Resposta do Google AI Studio não conteve embeddings para o modelo '{modelo}'"
            )

        resultado: list[list[float]] = []
        for item in embeddings:
            valores = (
                item.get("values") if isinstance(item, dict) else getattr(item, "values", None)
            )
            if valores is None:
                raise ErroBusca(
                    f"Item de embedding inválido na resposta do Google AI Studio ({modelo})"
                )
            resultado.append([float(x) for x in valores])

        if len(resultado) != quantidade_esperada:
            raise ErroBusca(
                f"Quantidade de vetores retornada ({len(resultado)}) difere da "
                f"quantidade de textos enviada ({quantidade_esperada})"
            )
        return resultado

    def _aguardar_pacing(self) -> None:
        intervalo = max(0.0, float(self.intervalo_entre_requisicoes_segundos))
        if intervalo <= 0.0:
            return
        with self._lock_pacing:
            agora = float(self.clock_fn())
            if self._ultimo_envio is not None:
                decorrido = agora - self._ultimo_envio
                restante = intervalo - decorrido
                if restante > 0.0:
                    self.sleep_fn(restante)
            self._ultimo_envio = float(self.clock_fn())

    def _calcular_backoff(self, tentativa: int) -> float:
        base = max(0.0, float(self.backoff_inicial_segundos))
        if base <= 0.0:
            return 0.0
        jitter = random.uniform(0.0, min(0.5, base * 0.25))
        return round(base * (2**tentativa) + jitter, 3)

    @staticmethod
    def _classificar_erro(exc: Exception) -> tuple[str, int | None]:
        status = getattr(exc, "code", None)
        if status is None:
            status = getattr(exc, "status_code", None)
        mensagem = str(getattr(exc, "message", "") or exc)
        detalhes = str(getattr(exc, "details", "") or "")
        status_str = str(getattr(exc, "status", "") or "")
        texto = f"{mensagem} {detalhes} {status_str}".lower()

        if status in (401, 403) or "api_key_invalid" in texto or "api key not valid" in texto:
            return "auth", status if isinstance(status, int) else None

        if isinstance(exc, (TimeoutError, OSError)) or status in CODIGOS_HTTP_TRANSITORIOS:
            return "transient", status if isinstance(status, int) else None

        if any(marcador in texto for marcador in MARCADORES_ERRO_TRANSITORIO):
            return "transient", status if isinstance(status, int) else None

        return "fatal", status if isinstance(status, int) else None

    def _sanitizar_mensagem(self, mensagem: str) -> str:
        chave = self.chave.strip()
        if chave and chave in mensagem:
            return mensagem.replace(chave, "***")
        return mensagem
