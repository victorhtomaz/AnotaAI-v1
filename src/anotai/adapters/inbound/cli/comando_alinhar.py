import argparse
import json
import sys
from pathlib import Path
from typing import Any

from anotai.adapters.inbound.cli.comando_buscar import (
    resolver_aula_cli,
    resolver_documento_cli,
)
from anotai.adapters.inbound.cli.formatador_terminal import formatar_alinhamento_texto
from anotai.application.use_cases import (
    AgrupadorIntervalos,
    AlinharAula,
    ImportarDocumento,
    RecuperarCandidatos,
    TranscreverAula,
    resolver_preset_alinhamento,
)
from anotai.bootstrap import (
    construir_indices_busca,
    criar_analisador_visual,
    criar_extrator_documento,
    criar_inspetor_audio,
    criar_provedor_transcricao,
    obter_classes_repositorios,
)
from anotai.config import Settings
from anotai.domain.exceptions import ErroBusca, ErroIntegridade
from anotai.domain.value_objects import (
    ParametrosHMM,
    PesosAlinhamento,
    ResultadoAlinhamentoIntervalo,
)


def configurar_parser_alinhar(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "alinhar",
        help="Executa alinhamento temporal e hierárquico ou registra revisão manual.",
    )
    parser.add_argument(
        "id_aula",
        type=str,
        nargs="?",
        default=None,
        help="ID, título ou arquivo da aula (opcional se houver 1 aula no banco).",
    )
    parser.add_argument(
        "id_documento",
        type=str,
        nargs="?",
        default=None,
        help="ID, título ou arquivo PDF (opcional se houver 1 documento no banco).",
    )
    parser.add_argument(
        "--modo",
        "--mode",
        choices=("padrao", "hmm", "rapido", "kernel", "semantico", "lexical"),
        default=None,
        help="Modo simplificado: 'hmm'/'padrao', 'rapido'/'kernel', 'semantico', 'lexical'.",
    )
    parser.add_argument(
        "--strategy",
        choices=(
            "bm25",
            "embedding",
            "hybrid",
            "temporal",
            "temporal_hmm",
            "hierarchical",
            "hierarchical_hmm",
        ),
        default=None,
        help="Estratégia avançada de alinhamento documental (padrão: hierarchical).",
    )
    parser.add_argument(
        "--base-strategy",
        choices=("bm25", "embedding", "hybrid"),
        default="bm25",
        help="Estratégia base de recuperação usada por temporal/hierarchical.",
    )
    parser.add_argument(
        "--temporal-model",
        choices=("kernel", "hmm"),
        default="kernel",
        help="Modelo temporal ('kernel' para vizinhança, 'hmm' para forward-backward).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Limiar mínimo de confiança para abstenção.",
    )
    parser.add_argument(
        "--temporal-weight",
        type=float,
        default=None,
        help="Peso do contexto temporal no modo kernel.",
    )
    parser.add_argument(
        "--visual-weight",
        type=float,
        default=None,
        help="Peso da evidência visual.",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=None,
        help="Janela de intervalos vizinhos para o modo kernel.",
    )
    parser.add_argument(
        "--hmm-temperature",
        type=float,
        default=None,
        help="Temperatura de emissão softmax do modelo HMM.",
    )
    parser.add_argument(
        "--max-paginas",
        type=int,
        default=3,
        help="Quantidade máxima de páginas alinhadas por intervalo.",
    )
    parser.add_argument(
        "--max-unidades",
        type=int,
        default=5,
        help="Quantidade máxima de unidades alinhadas por intervalo.",
    )
    parser.add_argument(
        "--intervalo",
        type=int,
        default=None,
        help="Número de ordem de um intervalo explicativo específico.",
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Registra revisão manual para o intervalo informado em --intervalo.",
    )
    parser.add_argument(
        "--paginas",
        type=str,
        default=None,
        help="IDs de páginas separados por vírgula para revisão manual.",
    )
    parser.add_argument(
        "--unidades",
        type=str,
        default=None,
        help="IDs de unidades separados por vírgula para revisão manual.",
    )
    parser.add_argument(
        "--abster",
        action="store_true",
        help="Marca abstenção explícita na revisão manual.",
    )
    parser.add_argument(
        "--justificativa",
        type=str,
        default=None,
        help="Justificativa para revisão manual.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Formato de saída.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Modelo de embedding Ollama (usado se base-strategy/strategy usar embedding).",
    )


def executar_comando_alinhar(
    args: argparse.Namespace,
    settings: Settings,
    repo_aula_cls: Any = None,
    repo_doc_cls: Any = None,
    repo_alin_cls: Any = None,
    recuperador_cls: Any = RecuperarCandidatos,
    alinhador_cls: Any = AlinharAula,
) -> int:
    padrao_doc_cls, padrao_aula_cls, padrao_alin_cls = obter_classes_repositorios()
    banco_path = Path(settings.database_path)
    repo_aula = (repo_aula_cls or padrao_aula_cls)(banco_path)
    repo_doc = (repo_doc_cls or padrao_doc_cls)(banco_path)
    repo_alin = (repo_alin_cls or padrao_alin_cls)(banco_path)

    id_aula_arg = getattr(args, "id_aula", None)
    id_doc_arg = getattr(args, "id_documento", None)

    # 1. Tolerância a inversão se arquivos forem passados (ex: pdf primeiro, audio depois)
    exts_audio = (".wav", ".mp3", ".m4a", ".mp4", ".mkv", ".webm")
    if (
        id_aula_arg
        and id_doc_arg
        and id_aula_arg.lower().endswith(".pdf")
        and any(id_doc_arg.lower().endswith(e) for e in exts_audio)
    ):
        id_aula_arg, id_doc_arg = id_doc_arg, id_aula_arg

    # 2. Ingestão transparente on-the-fly se arquivos locais forem fornecidos
    if id_doc_arg and Path(id_doc_arg).is_file() and id_doc_arg.lower().endswith(".pdf"):
        caminho_pdf = Path(id_doc_arg)
        doc_existente = resolver_documento_cli(repo_doc, str(caminho_pdf))
        if doc_existente is None:
            print(f"Indexando documento PDF '{caminho_pdf.name}'...")
            analisador = criar_analisador_visual(
                settings,
                settings.visual_model,
                temperatura=settings.visual_temperature,
                seed=settings.visual_seed,
                pensar=settings.visual_think,
            )
            caso_doc = ImportarDocumento(
                criar_extrator_documento(analisador), repositorio=repo_doc
            )
            doc_novo = caso_doc.executar(caminho_pdf, "native_then_ocr")
            id_doc_arg = doc_novo.id_documento

    if id_aula_arg and Path(id_aula_arg).is_file() and any(
        id_aula_arg.lower().endswith(e) for e in exts_audio
    ):
        caminho_audio = Path(id_aula_arg)
        aula_existente = resolver_aula_cli(repo_aula, str(caminho_audio))
        if aula_existente is None:
            print(f"Transcrevendo áudio '{caminho_audio.name}'...")
            inspetor = criar_inspetor_audio()
            provedor = criar_provedor_transcricao(
                modelo=settings.whisperx_model,
                dispositivo=settings.whisperx_device,
                tipo_computacao=settings.whisperx_compute_type,
                alinhar_fonemas=settings.whisperx_align_phonemes,
            )
            agrupador = AgrupadorIntervalos(
                limiar_silencio=settings.interval_silence_threshold,
                duracao_minima=settings.interval_min_duration,
                duracao_maxima=settings.interval_max_duration,
            )
            caso_transc = TranscreverAula(
                inspetor=inspetor,
                provedor=provedor,
                repositorio=repo_aula,
                agrupador=agrupador,
                diretorio_bruto=Path(settings.raw_transcripts_directory),
            )
            aula_nova = caso_transc.executar(caminho_audio)
            id_aula_arg = aula_nova.id_aula

    # 3. Resolução da aula e documento (com auto-seleção se houver apenas um)
    aula = resolver_aula_cli(repo_aula, id_aula_arg)
    if aula is None:
        return 1

    documento = resolver_documento_cli(repo_doc, id_doc_arg)
    if documento is None:
        return 1

    if id_aula_arg is None and id_doc_arg is None and getattr(args, "format", "text") == "text":
        print(f"Auto-selecionado: aula '{aula.titulo}' e documento '{documento.titulo}'.")

    if getattr(args, "manual", False):
        if args.intervalo is None:
            print(
                "Erro: Para revisão manual (--manual), informe --intervalo <N>.",
                file=sys.stderr,
            )
            return 1
        intervalos_alvo = [i for i in aula.intervalos if i.ordem == args.intervalo]
        if not intervalos_alvo:
            print(
                f"Aviso: Intervalo explicativo #{args.intervalo} não encontrado na aula.",
                file=sys.stderr,
            )
            return 1
        inter_alvo = intervalos_alvo[0]
        ids_paginas = (
            [p.strip() for p in args.paginas.split(",") if p.strip()]
            if getattr(args, "paginas", None)
            else []
        )
        ids_unidades = (
            [u.strip() for u in args.unidades.split(",") if u.strip()]
            if getattr(args, "unidades", None)
            else []
        )
        alinhador_manual = alinhador_cls(
            recuperador=None,
            repositorio_alinhamento=repo_alin,
        )
        try:
            alin_manual = alinhador_manual.registrar_revisao_manual(
                aula=aula,
                documento=documento,
                id_intervalo=inter_alvo.id_intervalo,
                ids_paginas=ids_paginas,
                ids_unidades=ids_unidades,
                abster=bool(getattr(args, "abster", False)),
                justificativa=getattr(args, "justificativa", None),
            )
        except (ErroIntegridade, ValueError) as exc:
            print(f"Erro na revisão manual: {exc}", file=sys.stderr)
            return 1

        resultados = [
            ResultadoAlinhamentoIntervalo(
                alinhamento=alin_manual,
                ordem_intervalo=inter_alvo.ordem,
                texto_intervalo=inter_alvo.texto,
                intervalo_tempo=inter_alvo.intervalo,
            )
        ]
        _imprimir_resultados_alinhamento(aula, documento, resultados, args.format)
        return 0

    # 4. Resolução simplificada do modo (--modo)
    modo = getattr(args, "modo", None)
    estrategia = getattr(args, "strategy", None)
    modelo_temporal = getattr(args, "temporal_model", "kernel")
    base_strategy = getattr(args, "base_strategy", "bm25")

    if isinstance(modo, str) and modo:
        estrategia, base_strategy, modelo_temporal = resolver_preset_alinhamento(modo)
    elif estrategia is None:
        # Padrão inteligente recomendado para o projeto
        estrategia = "hierarchical"
        modelo_temporal = "hmm"
        base_strategy = "bm25"

    estrategia_base = (
        estrategia
        if estrategia in ("bm25", "embedding", "hybrid")
        else base_strategy
    )
    idx_paginas, idx_unidades = construir_indices_busca(
        estrategia_base, settings, modelo_override=getattr(args, "model", None)
    )

    limiar = args.threshold if args.threshold is not None else settings.abstention_threshold
    recuperador = recuperador_cls(
        indice_paginas=idx_paginas,
        indice_unidades=idx_unidades,
        estrategia=estrategia_base,
        top_k_paginas=max(len(documento.paginas), 5),
        top_k_unidades=max(getattr(args, "max_unidades", 5) * 3, 10),
        limiar_abstencao=0.0,
    )

    pesos = PesosAlinhamento(
        peso_similaridade=settings.alignment_similarity_weight,
        peso_temporal=(
            args.temporal_weight
            if getattr(args, "temporal_weight", None) is not None
            else settings.alignment_temporal_weight
        ),
        peso_visual=(
            args.visual_weight
            if getattr(args, "visual_weight", None) is not None
            else settings.alignment_visual_weight
        ),
        janela_temporal=(
            args.window
            if getattr(args, "window", None) is not None
            else settings.alignment_temporal_window
        ),
    )

    params_hmm = ParametrosHMM(
        temperatura_emissao=(
            args.hmm_temperature
            if getattr(args, "hmm_temperature", None) is not None
            else settings.hmm_emission_temperature
        ),
        piso_emissao=settings.hmm_emission_floor,
        prior_abstencao_emissao=settings.hmm_abstention_emission_prior,
        peso_permanencia=settings.hmm_stay_weight,
        peso_adjacente=settings.hmm_adjacent_weight,
        peso_salto_base=settings.hmm_jump_base_weight,
        decaimento_salto=settings.hmm_jump_decay,
        piso_salto=settings.hmm_jump_floor,
    )

    alinhador = alinhador_cls(
        recuperador=recuperador,
        repositorio_alinhamento=repo_alin,
        estrategia=estrategia,
        modelo_temporal=modelo_temporal,
        pesos=pesos,
        parametros_hmm=params_hmm,
        limiar_abstencao=limiar,
        max_paginas=getattr(args, "max_paginas", 3),
        max_unidades=getattr(args, "max_unidades", 5),
    )

    try:
        resultados = alinhador.executar(aula, documento)
    except (ErroBusca, ErroIntegridade) as exc:
        print(f"Erro no alinhamento documental: {exc}", file=sys.stderr)
        return 1

    if args.intervalo is not None:
        resultados_filtrados = [r for r in resultados if r.ordem_intervalo == args.intervalo]
        if not resultados_filtrados:
            print(
                f"Aviso: Intervalo explicativo #{args.intervalo} não encontrado na aula.",
                file=sys.stderr,
            )
            return 1
        resultados = resultados_filtrados

    _imprimir_resultados_alinhamento(aula, documento, resultados, args.format)
    return 0


def _imprimir_resultados_alinhamento(
    aula: Any,
    documento: Any,
    resultados: list[ResultadoAlinhamentoIntervalo],
    formato: str,
) -> None:
    if formato == "json":
        saida_json = [
            {
                "id_alinhamento": r.alinhamento.id_alinhamento,
                "id_intervalo": r.alinhamento.id_intervalo,
                "ordem_intervalo": r.ordem_intervalo,
                "texto_intervalo": r.texto_intervalo,
                "inicio": r.intervalo_tempo.inicio,
                "fim": r.intervalo_tempo.fim,
                "status": r.alinhamento.status,
                "origem": r.alinhamento.origem,
                "estrategia": r.alinhamento.estrategia,
                "tipo_relacao": r.alinhamento.tipo_relacao,
                "confianca": r.alinhamento.confianca,
                "ids_paginas": r.alinhamento.ids_paginas,
                "ids_unidades": r.alinhamento.ids_unidades,
                "ids_evidencias": r.alinhamento.ids_evidencias,
                "justificativa": r.alinhamento.justificativa,
                "probabilidade_abstencao_hmm": r.probabilidade_abstencao_hmm,
                "candidatos_pagina": [
                    {
                        "id_pagina": cp.id_item,
                        "numero_pagina": cp.numero_pagina,
                        "pontuacao_similaridade": cp.pontuacao_similaridade,
                        "pontuacao_temporal": cp.pontuacao_temporal,
                        "pontuacao_visual": cp.pontuacao_visual,
                        "pontuacao_final": cp.pontuacao_final,
                        "selecionado": cp.selecionado,
                    }
                    for cp in r.candidatos_pagina
                ],
                "candidatos_unidade": [
                    {
                        "id_unidade": cu.id_item,
                        "id_pagina": cu.id_pagina,
                        "numero_pagina": cu.numero_pagina,
                        "tipo_unidade": cu.tipo_unidade,
                        "ordem_leitura": cu.ordem_leitura,
                        "pontuacao_similaridade": cu.pontuacao_similaridade,
                        "pontuacao_temporal": cu.pontuacao_temporal,
                        "pontuacao_visual": cu.pontuacao_visual,
                        "pontuacao_final": cu.pontuacao_final,
                        "selecionado": cu.selecionado,
                    }
                    for cu in r.candidatos_unidade
                ],
            }
            for r in resultados
        ]
        print(json.dumps(saida_json, ensure_ascii=False, indent=2))
    else:
        print(formatar_alinhamento_texto(aula, documento, resultados))
