import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from anotai.application.ports.repositorio_aula import RepositorioAula
from anotai.domain.entities import (
    Aula,
    IntervaloExplicativo,
    SegmentoTranscricao,
    ValidadorIntegridade,
)
from anotai.domain.value_objects import IntervaloTempo, MetadadosAudio

from .base import Base, criar_engine_sqlite
from .modelo_aula import ModeloAula, ModeloIntervaloExplicativo, ModeloSegmentoTranscricao


class RepositorioAulaSQLite(RepositorioAula):
    def __init__(self, caminho_banco: Path) -> None:
        self.caminho_banco = caminho_banco
        self._engine = criar_engine_sqlite(caminho_banco)
        Base.metadata.create_all(self._engine)

    def salvar(self, aula: Aula, carga_bruta_asr: dict[str, Any] | None = None) -> None:
        ValidadorIntegridade.validar_aula(aula)

        with Session(self._engine) as sessao:
            carga_json = (
                json.dumps(carga_bruta_asr, ensure_ascii=False) if carga_bruta_asr else None
            )

            existente = sessao.get(ModeloAula, aula.id_aula)
            if existente is not None:
                existente.titulo = aula.titulo
                existente.uri_origem = aula.uri_origem
                existente.duracao = aula.metadados.duracao
                existente.taxa_amostragem = aula.metadados.taxa_amostragem
                existente.canais = aula.metadados.canais
                existente.formato = aula.metadados.formato
                existente.codec = aula.metadados.codec
                existente.taxa_bits = aula.metadados.taxa_bits
                existente.idioma = aula.idioma
                existente.versao_processamento = aula.versao_processamento
                existente.carga_bruta_asr = carga_json
                existente.segmentos.clear()
                existente.intervalos.clear()
                registro_aula = existente
            else:
                registro_aula = ModeloAula(
                    id=aula.id_aula,
                    titulo=aula.titulo,
                    uri_origem=aula.uri_origem,
                    duracao=aula.metadados.duracao,
                    taxa_amostragem=aula.metadados.taxa_amostragem,
                    canais=aula.metadados.canais,
                    formato=aula.metadados.formato,
                    codec=aula.metadados.codec,
                    taxa_bits=aula.metadados.taxa_bits,
                    idioma=aula.idioma,
                    versao_processamento=aula.versao_processamento,
                    carga_bruta_asr=carga_json,
                )
                sessao.add(registro_aula)

            for seg in aula.segmentos:
                palavras = json.dumps(seg.palavras, ensure_ascii=False) if seg.palavras else None
                registro_aula.segmentos.append(
                    ModeloSegmentoTranscricao(
                        id=seg.id_segmento,
                        aula_id=seg.id_aula,
                        texto=seg.texto,
                        inicio=seg.intervalo.inicio,
                        fim=seg.intervalo.fim,
                        ordem=seg.ordem,
                        fonte=seg.fonte,
                        confianca=seg.confianca,
                        palavras_json=palavras,
                    )
                )

            for inter in aula.intervalos:
                registro_aula.intervalos.append(
                    ModeloIntervaloExplicativo(
                        id=inter.id_intervalo,
                        aula_id=inter.id_aula,
                        texto=inter.texto,
                        inicio=inter.intervalo.inicio,
                        fim=inter.intervalo.fim,
                        ordem=inter.ordem,
                        tipo=inter.tipo,
                        notas=inter.notas,
                        ids_segmentos_json=json.dumps(inter.ids_segmentos, ensure_ascii=False),
                    )
                )

            sessao.add(registro_aula)
            sessao.commit()

    def buscar_por_id(self, id_aula: str) -> Aula | None:
        with Session(self._engine) as sessao:
            stmt = (
                select(ModeloAula)
                .where(ModeloAula.id == id_aula)
                .options(
                    selectinload(ModeloAula.segmentos),
                    selectinload(ModeloAula.intervalos),
                )
            )
            registro = sessao.scalars(stmt).first()
            if registro is None:
                return None
            return self._mapear_para_dominio(registro)

    def listar(self) -> list[Aula]:
        with Session(self._engine) as sessao:
            stmt = (
                select(ModeloAula)
                .options(
                    selectinload(ModeloAula.segmentos),
                    selectinload(ModeloAula.intervalos),
                )
                .order_by(ModeloAula.titulo)
            )
            registros = sessao.scalars(stmt).all()
            return [self._mapear_para_dominio(r) for r in registros]

    def buscar_por_termo(self, termo: str) -> list[tuple[str, str]]:
        termo_limpo = termo.strip()
        with Session(self._engine) as sessao:
            stmt = select(ModeloAula.id, ModeloAula.titulo).where(
                (ModeloAula.id.contains(termo_limpo))
                | (ModeloAula.titulo.ilike(f"%{termo_limpo}%"))
            )
            return [(row[0], row[1]) for row in sessao.execute(stmt)]

    @staticmethod
    def _mapear_para_dominio(registro: ModeloAula) -> Aula:
        metadados = MetadadosAudio(
            duracao=registro.duracao,
            taxa_amostragem=registro.taxa_amostragem,
            canais=registro.canais,
            formato=registro.formato,
            codec=registro.codec,
            taxa_bits=registro.taxa_bits,
        )

        segmentos = [
            SegmentoTranscricao(
                id_segmento=s.id,
                id_aula=s.aula_id,
                texto=s.texto,
                intervalo=IntervaloTempo(s.inicio, s.fim),
                ordem=s.ordem,
                fonte=s.fonte,
                confianca=s.confianca,
                palavras=json.loads(s.palavras_json) if s.palavras_json else [],
            )
            for s in registro.segmentos
        ]

        intervalos = [
            IntervaloExplicativo(
                id_intervalo=i.id,
                id_aula=i.aula_id,
                texto=i.texto,
                intervalo=IntervaloTempo(i.inicio, i.fim),
                ordem=i.ordem,
                tipo=i.tipo,
                notas=i.notas,
                ids_segmentos=json.loads(i.ids_segmentos_json) if i.ids_segmentos_json else [],
            )
            for i in registro.intervalos
        ]

        return Aula(
            id_aula=registro.id,
            titulo=registro.titulo,
            uri_origem=registro.uri_origem,
            caminho_arquivo=Path(registro.uri_origem),
            metadados=metadados,
            segmentos=segmentos,
            intervalos=intervalos,
            idioma=registro.idioma,
            versao_processamento=registro.versao_processamento,
        )
