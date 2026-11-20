from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from starlette.datastructures import FormData, UploadFile

from anotai.config import Settings

from .gerenciador_processamento import OpcoesProcessamento, higienizar_nome_arquivo

TAMANHO_CHUNK_UPLOAD = 1024 * 1024  # 1 MiB


def _flag(form: FormData, chave: str) -> bool:
    return str(form.get(chave, "")).strip().lower() in ("on", "true", "1", "sim")


def _texto(form: FormData, chave: str, padrao: str = "") -> str:
    valor = form.get(chave)
    if valor is None or isinstance(valor, UploadFile):
        return padrao
    return str(valor).strip()


def _inteiro(form: FormData, chave: str, padrao: int, minimo: int | None = None) -> int:
    bruto = _texto(form, chave)
    if not bruto:
        return padrao
    try:
        valor = int(bruto)
    except ValueError as exc:
        raise ValueError(f"Valor inteiro inválido para '{chave}': '{bruto}'.") from exc
    if minimo is not None and valor < minimo:
        raise ValueError(f"O campo '{chave}' deve ser maior ou igual a {minimo}.")
    return valor


def _decimal(
    form: FormData,
    chave: str,
    padrao: float,
    minimo: float | None = None,
    maximo: float | None = None,
) -> float:
    bruto = _texto(form, chave).replace(",", ".")
    if not bruto:
        return padrao
    try:
        valor = float(bruto)
    except ValueError as exc:
        raise ValueError(f"Valor numérico inválido para '{chave}': '{bruto}'.") from exc
    if minimo is not None and valor < minimo:
        raise ValueError(f"O campo '{chave}' deve ser maior ou igual a {minimo}.")
    if maximo is not None and valor > maximo:
        raise ValueError(f"O campo '{chave}' deve ser menor ou igual a {maximo}.")
    return valor


def extrair_opcoes(form: FormData, settings: Settings) -> OpcoesProcessamento:
    """Extrai e valida as opções do formulário de processamento em relação aos limites."""
    padrao = OpcoesProcessamento.a_partir_de_settings(settings)

    metodo_pdf = _texto(form, "metodo_pdf", padrao.metodo_pdf)
    if metodo_pdf not in ("native_then_ocr", "native"):
        raise ValueError(f"Método de extração de PDF inválido: '{metodo_pdf}'.")

    provedor_visual = (
        _texto(form, "provedor_visual", padrao.provedor_visual) or padrao.provedor_visual
    ).lower()
    if provedor_visual not in ("ollama", "google_ai_studio"):
        raise ValueError(f"Provedor de análise visual inválido: '{provedor_visual}'.")

    provedor_transcricao = (
        _texto(form, "provedor_transcricao", padrao.provedor_transcricao)
        or padrao.provedor_transcricao
    ).lower()
    if provedor_transcricao not in ("whisperx", "azure_speech"):
        raise ValueError(f"Provedor de transcrição inválido: '{provedor_transcricao}'.")

    idioma_transcricao = (
        _texto(form, "idioma_transcricao", padrao.idioma_transcricao)
        or padrao.idioma_transcricao
    )

    duracao_min = _decimal(form, "duracao_minima_intervalo", padrao.duracao_minima_intervalo, 1.0)
    duracao_max = _decimal(form, "duracao_maxima_intervalo", padrao.duracao_maxima_intervalo, 1.0)
    if duracao_max < duracao_min:
        raise ValueError(
            "A duração máxima do intervalo explicativo deve ser maior ou igual à duração mínima."
        )

    return OpcoesProcessamento(
        executar_pdf=_flag(form, "executar_pdf"),
        executar_transcricao=_flag(form, "executar_transcricao"),
        executar_alinhamento=_flag(form, "executar_alinhamento"),
        id_documento_existente=_texto(form, "id_documento_existente") or None,
        id_aula_existente=_texto(form, "id_aula_existente") or None,
        metodo_pdf=metodo_pdf,
        provedor_visual=provedor_visual,
        modelo_visual=_texto(form, "modelo_visual", padrao.modelo_visual) or padrao.modelo_visual,
        temperatura_visual=_decimal(
            form, "temperatura_visual", padrao.temperatura_visual, 0.0, 2.0
        ),
        seed_visual=_inteiro(form, "seed_visual", padrao.seed_visual, 0),
        pensar_visual=_flag(form, "pensar_visual"),
        titulo_aula=_texto(form, "titulo_aula") or None,
        provedor_transcricao=provedor_transcricao,
        idioma_transcricao=idioma_transcricao,
        modelo_whisperx=(
            _texto(form, "modelo_whisperx", padrao.modelo_whisperx) or padrao.modelo_whisperx
        ),
        dispositivo_whisperx=(
            _texto(form, "dispositivo_whisperx", padrao.dispositivo_whisperx)
            or padrao.dispositivo_whisperx
        ),
        tipo_computacao=(
            _texto(form, "tipo_computacao", padrao.tipo_computacao) or padrao.tipo_computacao
        ),
        alinhar_fonemas=_flag(form, "alinhar_fonemas"),
        limiar_silencio=_decimal(form, "limiar_silencio", padrao.limiar_silencio, 0.1),
        duracao_minima_intervalo=duracao_min,
        duracao_maxima_intervalo=duracao_max,
        modo_alinhamento=_texto(form, "modo_alinhamento", padrao.modo_alinhamento),
        estrategia_alinhamento=_texto(
            form, "estrategia_alinhamento", padrao.estrategia_alinhamento
        ),
        estrategia_base=_texto(form, "estrategia_base", padrao.estrategia_base),
        modelo_temporal=_texto(form, "modelo_temporal", padrao.modelo_temporal),
        modelo_embedding=(
            _texto(form, "modelo_embedding", padrao.modelo_embedding) or padrao.modelo_embedding
        ),
        limiar_abstencao=_decimal(form, "limiar_abstencao", padrao.limiar_abstencao, 0.0, 1.0),
        max_paginas=_inteiro(form, "max_paginas", padrao.max_paginas, 1),
        max_unidades=_inteiro(form, "max_unidades", padrao.max_unidades, 1),
        peso_similaridade=_decimal(form, "peso_similaridade", padrao.peso_similaridade, 0.0, 1.0),
        peso_temporal=_decimal(form, "peso_temporal", padrao.peso_temporal, 0.0, 1.0),
        peso_visual=_decimal(form, "peso_visual", padrao.peso_visual, 0.0, 1.0),
        janela_temporal=_inteiro(form, "janela_temporal", padrao.janela_temporal, 0),
        temperatura_hmm=_decimal(form, "temperatura_hmm", padrao.temperatura_hmm, 0.01, 5.0),
    )


async def salvar_arquivo_se_enviado(
    campo: Any,
    diretorio_uploads: Path,
    extensoes_permitidas: tuple[str, ...],
    rotulo_tipo: str,
    *,
    etapa_habilitada: bool = True,
) -> Path | None:
    """Grava upload em chunks sem manter o arquivo inteiro em RAM quando a etapa está ativa."""
    if not etapa_habilitada:
        return None
    if not isinstance(campo, UploadFile) or not campo.filename or not campo.filename.strip():
        return None

    sufixo_original = Path(campo.filename).suffix.lower()
    if sufixo_original not in extensoes_permitidas:
        permitidas = ", ".join(extensoes_permitidas)
        raise ValueError(
            f"Formato inválido para {rotulo_tipo} ('{campo.filename}'). Permitidos: {permitidas}."
        )

    diretorio_uploads.mkdir(parents=True, exist_ok=True)
    caminho_tmp = diretorio_uploads / f".upload-{uuid.uuid4().hex}.tmp"
    hasher = hashlib.sha256()
    total_bytes = 0

    try:
        with caminho_tmp.open("wb") as destino:
            while True:
                bloco = await campo.read(TAMANHO_CHUNK_UPLOAD)
                if not bloco:
                    break
                destino.write(bloco)
                hasher.update(bloco)
                total_bytes += len(bloco)

        if total_bytes == 0:
            caminho_tmp.unlink(missing_ok=True)
            raise ValueError(
                f"O arquivo enviado para {rotulo_tipo} ('{campo.filename}') está vazio."
            )

        nome_seguro = higienizar_nome_arquivo(campo.filename)
        caminho_final = diretorio_uploads / nome_seguro
        if caminho_final.exists():
            digest = hasher.hexdigest()[:8]
            stem = Path(nome_seguro).stem
            sufixo = Path(nome_seguro).suffix
            caminho_final = diretorio_uploads / f"{stem}-{digest}{sufixo}"

        caminho_tmp.replace(caminho_final)
        return caminho_final
    except Exception:
        caminho_tmp.unlink(missing_ok=True)
        raise
