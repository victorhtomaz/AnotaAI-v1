from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from anotai.application.ports.repositorio_anotacao import RepositorioAnotacao
from anotai.domain.entities import Anotacao
from anotai.domain.exceptions import ErroIntegridade
from anotai.domain.value_objects import IntervaloTempo

from .base import inicializar_engine_sqlite
from .modelo_anotacao import (
    ModeloAnotacao,
    ModeloAnotacaoPagina,
    ModeloAnotacaoUnidade,
)
from .modelo_documento import ModeloUnidade


class RepositorioAnotacaoSQLite(RepositorioAnotacao):
    def __init__(self, caminho_banco: Path, engine: Engine | None = None) -> None:
        self.caminho_banco = caminho_banco
        self._engine = engine if engine is not None else inicializar_engine_sqlite(caminho_banco)

    def salvar(self, anotacao: Anotacao) -> None:
        with Session(self._engine) as sessao:
            try:
                self._salvar_com_sessao(sessao, anotacao)
                sessao.commit()
            except IntegrityError as exc:
                sessao.rollback()
                raise ErroIntegridade(
                    f"Falha de integridade referencial ao salvar anotação: {exc.orig}"
                ) from exc

    def salvar_lote(self, anotacoes: list[Anotacao]) -> None:
        with Session(self._engine) as sessao:
            try:
                for anotacao in anotacoes:
                    self._salvar_com_sessao(sessao, anotacao)
                sessao.commit()
            except IntegrityError as exc:
                sessao.rollback()
                raise ErroIntegridade(
                    f"Falha de integridade referencial ao salvar lote de anotações: {exc.orig}"
                ) from exc

    def _salvar_com_sessao(self, sessao: Session, anotacao: Anotacao) -> None:
        self._validar_regras_negocio(sessao, anotacao)
        existente = sessao.get(ModeloAnotacao, anotacao.id_anotacao)
        if existente is not None:
            sessao.delete(existente)
            sessao.flush()

        registro = ModeloAnotacao(
            id=anotacao.id_anotacao,
            aula_id=anotacao.id_aula,
            documento_id=anotacao.id_documento,
            intervalo_id=anotacao.id_intervalo,
            inicio=anotacao.intervalo.inicio,
            fim=anotacao.intervalo.fim,
            tipo_relacao=anotacao.tipo_relacao,
            notas=anotacao.notas,
            versao=anotacao.versao,
        )

        for idx, id_pag in enumerate(anotacao.ids_paginas, start=1):
            registro.paginas_relacionadas.append(
                ModeloAnotacaoPagina(
                    anotacao_id=anotacao.id_anotacao,
                    pagina_id=id_pag,
                    ordem=idx,
                )
            )

        for idx, id_unidade in enumerate(anotacao.ids_unidades, start=1):
            registro.unidades_relacionadas.append(
                ModeloAnotacaoUnidade(
                    anotacao_id=anotacao.id_anotacao,
                    unidade_id=id_unidade,
                    ordem=idx,
                )
            )

        sessao.add(registro)

    @classmethod
    def _validar_regras_negocio(cls, sessao: Session, anotacao: Anotacao) -> None:
        """Valida regras de negócio semânticas que o SQLite não valida via FK."""
        if anotacao.ids_unidades:
            decorativa = sessao.scalars(
                select(ModeloUnidade.id).where(
                    ModeloUnidade.id.in_(anotacao.ids_unidades),
                    ModeloUnidade.eh_decorativa.is_(True),
                )
            ).first()
            if decorativa:
                raise ErroIntegridade(
                    f"Unidade '{decorativa}' é marcada como decorativa e "
                    "não pode participar de anotação"
                )

            inconsistente = sessao.scalars(
                select(ModeloUnidade.id).where(
                    ModeloUnidade.id.in_(anotacao.ids_unidades),
                    ModeloUnidade.pagina_id.not_in(anotacao.ids_paginas),
                )
            ).first()
            if inconsistente:
                raise ErroIntegridade(
                    f"Inconsistência hierárquica: unidade '{inconsistente}' pertence à página "
                    "que não foi incluída em ids_paginas da anotação"
                )

    def buscar_por_id(self, id_anotacao: str) -> Anotacao | None:
        with Session(self._engine) as sessao:
            registro = sessao.get(ModeloAnotacao, id_anotacao)
            if registro is None:
                return None
            return self._mapear_para_dominio(registro)

    def listar_por_aula(
        self,
        id_aula: str,
        id_documento: str | None = None,
        versao: str | None = None,
    ) -> list[Anotacao]:
        with Session(self._engine) as sessao:
            stmt = select(ModeloAnotacao).where(ModeloAnotacao.aula_id == id_aula)
            if id_documento:
                stmt = stmt.where(ModeloAnotacao.documento_id == id_documento)
            if versao:
                stmt = stmt.where(ModeloAnotacao.versao == versao)
            stmt = stmt.order_by(ModeloAnotacao.inicio)
            registros = sessao.scalars(stmt).all()
            return [self._mapear_para_dominio(r) for r in registros]

    def listar_por_intervalo(
        self, id_intervalo: str, versao: str | None = None
    ) -> list[Anotacao]:
        with Session(self._engine) as sessao:
            stmt = select(ModeloAnotacao).where(ModeloAnotacao.intervalo_id == id_intervalo)
            if versao:
                stmt = stmt.where(ModeloAnotacao.versao == versao)
            stmt = stmt.order_by(ModeloAnotacao.inicio)
            registros = sessao.scalars(stmt).all()
            return [self._mapear_para_dominio(r) for r in registros]

    @classmethod
    def _mapear_para_dominio(cls, registro: ModeloAnotacao) -> Anotacao:
        ids_paginas = [
            rel.pagina_id
            for rel in sorted(registro.paginas_relacionadas, key=lambda x: x.ordem)
        ]
        ids_unidades = [
            rel.unidade_id
            for rel in sorted(registro.unidades_relacionadas, key=lambda x: x.ordem)
        ]

        return Anotacao(
            id_anotacao=registro.id,
            id_aula=registro.aula_id,
            id_documento=registro.documento_id,
            intervalo=IntervaloTempo(registro.inicio, registro.fim),
            id_intervalo=registro.intervalo_id,
            ids_paginas=ids_paginas,
            ids_unidades=ids_unidades,
            tipo_relacao=registro.tipo_relacao,
            notas=registro.notas,
            versao=registro.versao,
        )
