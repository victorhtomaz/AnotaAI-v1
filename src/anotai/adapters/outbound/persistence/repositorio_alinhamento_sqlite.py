import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from anotai.application.ports.repositorio_alinhamento import RepositorioAlinhamento
from anotai.domain.entities import Alinhamento
from anotai.domain.exceptions import ErroIntegridade

from .base import Base, criar_engine_sqlite
from .modelo_alinhamento import (
    ModeloAlinhamento,
    ModeloAlinhamentoPagina,
    ModeloAlinhamentoUnidade,
)
from .modelo_documento import ModeloUnidade


class RepositorioAlinhamentoSQLite(RepositorioAlinhamento):
    def __init__(self, caminho_banco: Path) -> None:
        self.caminho_banco = caminho_banco
        self._engine = criar_engine_sqlite(caminho_banco)
        Base.metadata.create_all(self._engine)

    def salvar(self, alinhamento: Alinhamento) -> None:
        with Session(self._engine) as sessao:
            try:
                self._salvar_com_sessao(sessao, alinhamento)
                sessao.commit()
            except IntegrityError as exc:
                sessao.rollback()
                raise ErroIntegridade(
                    f"Falha de integridade referencial ao salvar alinhamento: {exc.orig}"
                ) from exc

    def salvar_lote(self, alinhamentos: list[Alinhamento]) -> None:
        with Session(self._engine) as sessao:
            try:
                for alinhamento in alinhamentos:
                    self._salvar_com_sessao(sessao, alinhamento)
                sessao.commit()
            except IntegrityError as exc:
                sessao.rollback()
                raise ErroIntegridade(
                    f"Falha de integridade referencial ao salvar lote de alinhamentos: {exc.orig}"
                ) from exc

    def _salvar_com_sessao(self, sessao: Session, alinhamento: Alinhamento) -> None:
        self._validar_regras_negocio(sessao, alinhamento)

        # Reprocessamento idempotente: se já existe para a mesma tupla
        # (intervalo_id, documento_id, estrategia, origem), substitui
        stmt_existente = select(ModeloAlinhamento).where(
            ModeloAlinhamento.intervalo_id == alinhamento.id_intervalo,
            ModeloAlinhamento.documento_id == alinhamento.id_documento,
            ModeloAlinhamento.estrategia == alinhamento.estrategia,
            ModeloAlinhamento.origem == alinhamento.origem,
        )
        existente = sessao.scalars(stmt_existente).first()

        # Também verifica por ID direto caso a chave natural seja diferente
        if existente is None:
            existente = sessao.get(ModeloAlinhamento, alinhamento.id_alinhamento)

        if existente is not None:
            sessao.delete(existente)
            sessao.flush()

        registro = ModeloAlinhamento(
            id=alinhamento.id_alinhamento,
            aula_id=alinhamento.id_aula,
            documento_id=alinhamento.id_documento,
            intervalo_id=alinhamento.id_intervalo,
            status=alinhamento.status,
            tipo_relacao=alinhamento.tipo_relacao,
            confianca=alinhamento.confianca,
            estrategia=alinhamento.estrategia,
            versao_processamento=alinhamento.versao_processamento,
            justificativa=alinhamento.justificativa,
            origem=alinhamento.origem,
            ids_evidencias_json=json.dumps(alinhamento.ids_evidencias, ensure_ascii=False),
        )

        for idx, id_pag in enumerate(alinhamento.ids_paginas, start=1):
            registro.paginas_relacionadas.append(
                ModeloAlinhamentoPagina(
                    alinhamento_id=alinhamento.id_alinhamento,
                    pagina_id=id_pag,
                    ordem=idx,
                )
            )

        for idx, id_unidade in enumerate(alinhamento.ids_unidades, start=1):
            registro.unidades_relacionadas.append(
                ModeloAlinhamentoUnidade(
                    alinhamento_id=alinhamento.id_alinhamento,
                    unidade_id=id_unidade,
                    ordem=idx,
                )
            )

        sessao.add(registro)

    @classmethod
    def _validar_regras_negocio(cls, sessao: Session, alinhamento: Alinhamento) -> None:
        """Valida regras de negócio semânticas que o SQLite não valida via FK."""
        if alinhamento.ids_unidades:
            decorativa = sessao.scalars(
                select(ModeloUnidade.id).where(
                    ModeloUnidade.id.in_(alinhamento.ids_unidades),
                    ModeloUnidade.eh_decorativa.is_(True),
                )
            ).first()
            if decorativa:
                raise ErroIntegridade(
                    f"Unidade '{decorativa}' é marcada como decorativa e "
                    "não pode participar de alinhamento"
                )

            inconsistente = sessao.scalars(
                select(ModeloUnidade.id).where(
                    ModeloUnidade.id.in_(alinhamento.ids_unidades),
                    ModeloUnidade.pagina_id.not_in(alinhamento.ids_paginas),
                )
            ).first()
            if inconsistente:
                raise ErroIntegridade(
                    f"Inconsistência hierárquica: unidade '{inconsistente}' pertence à página "
                    "que não foi incluída em ids_paginas do alinhamento"
                )

    def buscar_por_id(self, id_alinhamento: str) -> Alinhamento | None:
        with Session(self._engine) as sessao:
            registro = sessao.get(ModeloAlinhamento, id_alinhamento)
            if registro is None:
                return None
            return self._mapear_para_dominio(registro)

    def listar_por_intervalo(
        self, id_intervalo: str, estrategia: str | None = None
    ) -> list[Alinhamento]:
        with Session(self._engine) as sessao:
            stmt = select(ModeloAlinhamento).where(
                ModeloAlinhamento.intervalo_id == id_intervalo
            )
            if estrategia:
                stmt = stmt.where(ModeloAlinhamento.estrategia == estrategia)
            registros = sessao.scalars(stmt).all()
            return [self._mapear_para_dominio(r) for r in registros]

    def listar_por_aula(
        self,
        id_aula: str,
        id_documento: str | None = None,
        estrategia: str | None = None,
    ) -> list[Alinhamento]:
        with Session(self._engine) as sessao:
            stmt = select(ModeloAlinhamento).where(ModeloAlinhamento.aula_id == id_aula)
            if id_documento:
                stmt = stmt.where(ModeloAlinhamento.documento_id == id_documento)
            if estrategia:
                stmt = stmt.where(ModeloAlinhamento.estrategia == estrategia)
            registros = sessao.scalars(stmt).all()
            return [self._mapear_para_dominio(r) for r in registros]

    def listar_por_pagina(
        self, id_pagina: str, estrategia: str | None = None
    ) -> list[Alinhamento]:
        with Session(self._engine) as sessao:
            stmt = (
                select(ModeloAlinhamento)
                .join(ModeloAlinhamento.paginas_relacionadas)
                .where(ModeloAlinhamentoPagina.pagina_id == id_pagina)
            )
            if estrategia:
                stmt = stmt.where(ModeloAlinhamento.estrategia == estrategia)
            registros = sessao.scalars(stmt).all()
            return [self._mapear_para_dominio(r) for r in registros]

    def listar_por_unidade(
        self, id_unidade: str, estrategia: str | None = None
    ) -> list[Alinhamento]:
        with Session(self._engine) as sessao:
            stmt = (
                select(ModeloAlinhamento)
                .join(ModeloAlinhamento.unidades_relacionadas)
                .where(ModeloAlinhamentoUnidade.unidade_id == id_unidade)
            )
            if estrategia:
                stmt = stmt.where(ModeloAlinhamento.estrategia == estrategia)
            registros = sessao.scalars(stmt).all()
            return [self._mapear_para_dominio(r) for r in registros]

    @classmethod
    def _mapear_para_dominio(cls, registro: ModeloAlinhamento) -> Alinhamento:
        ids_paginas = [
            rel.pagina_id
            for rel in sorted(registro.paginas_relacionadas, key=lambda x: x.ordem)
        ]
        ids_unidades = [
            rel.unidade_id
            for rel in sorted(registro.unidades_relacionadas, key=lambda x: x.ordem)
        ]
        evidencias = (
            json.loads(registro.ids_evidencias_json)
            if registro.ids_evidencias_json
            else []
        )

        return Alinhamento(
            id_alinhamento=registro.id,
            id_aula=registro.aula_id,
            id_documento=registro.documento_id,
            id_intervalo=registro.intervalo_id,
            ids_paginas=ids_paginas,
            ids_unidades=ids_unidades,
            status=registro.status,
            tipo_relacao=registro.tipo_relacao,
            confianca=registro.confianca,
            estrategia=registro.estrategia,
            ids_evidencias=evidencias,
            versao_processamento=registro.versao_processamento,
            justificativa=registro.justificativa,
            origem=registro.origem,
        )
