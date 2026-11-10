import json
from pathlib import Path

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from anotai.application.ports.repositorio_documento import (
    RepositorioDocumento as RepositorioDocumentoPort,
)
from anotai.domain.entities.Documento import Documento, PaginaDocumento, UnidadeDocumento
from anotai.domain.entities.ValidadorIntegridade import ValidadorIntegridade
from anotai.domain.value_objects.CaixaDelimitadora import CaixaDelimitadora
from anotai.domain.value_objects.ProvenienciaDocumento import ProvenienciaDocumento

from .base import Base, criar_engine_sqlite
from .modelo_documento import (
    ModeloDocumento,
    ModeloPagina,
    ModeloProveniencia,
    ModeloUnidade,
)


class RepositorioDocumento(RepositorioDocumentoPort):
    def __init__(self, caminho_banco: Path) -> None:
        self.caminho_banco = caminho_banco
        self._engine = criar_engine_sqlite(caminho_banco)
        Base.metadata.create_all(self._engine)
        self._garantir_coluna_decorativa()

    def _garantir_coluna_decorativa(self) -> None:
        colunas = {coluna["name"] for coluna in inspect(self._engine).get_columns("unidades")}
        if "eh_decorativa" not in colunas:
            with self._engine.begin() as conexao:
                conexao.exec_driver_sql(
                    "ALTER TABLE unidades ADD COLUMN eh_decorativa BOOLEAN NOT NULL DEFAULT 0"
                )

    def salvar(self, documento: Documento) -> None:
        ValidadorIntegridade.validar_documento(documento)

        with Session(self._engine) as sessao:
            existente = sessao.get(ModeloDocumento, documento.id_documento)
            if existente is not None:
                sessao.delete(existente)
                sessao.flush()

            registro = ModeloDocumento(
                id=documento.id_documento,
                uri_origem=documento.uri_origem,
                titulo=documento.titulo,
                versao_processamento=documento.versao_processamento,
                proveniencia=ModeloProveniencia(
                    uri_origem=documento.proveniencia.uri_origem,
                    metodo_extracao=documento.proveniencia.metodo_extracao,
                    versao_pipeline=documento.proveniencia.versao_pipeline,
                    modelo=documento.proveniencia.modelo,
                    configuracao=json.dumps(documento.proveniencia.configuracao)
                    if documento.proveniencia.configuracao
                    else None,
                    prompt=documento.proveniencia.prompt,
                    executado_em=documento.proveniencia.executado_em,
                ),
            )
            for pagina in documento.paginas:
                pagina_registro = ModeloPagina(
                    id=pagina.id_pagina,
                    numero=pagina.numero_pagina,
                    texto_nativo=pagina.texto_nativo,
                    texto_normalizado=pagina.texto_normalizado,
                    metodo_extracao=pagina.metodo_extracao,
                )
                for unidade in pagina.unidades:
                    caixa = unidade.caixa
                    pagina_registro.unidades.append(
                        ModeloUnidade(
                            id=unidade.id_unidade,
                            documento_id=unidade.id_documento,
                            pagina_id=unidade.id_pagina,
                            tipo=unidade.tipo,
                            texto=unidade.texto,
                            ordem_leitura=unidade.ordem_leitura,
                            x0=caixa.x0 if caixa else None,
                            y0=caixa.y0 if caixa else None,
                            x1=caixa.x1 if caixa else None,
                            y1=caixa.y1 if caixa else None,
                            fonte=unidade.fonte,
                            ids_evidencias=json.dumps(unidade.ids_evidencias),
                            eh_decorativa=unidade.eh_decorativa,
                        )
                    )
                registro.paginas.append(pagina_registro)

            sessao.add(registro)
            sessao.commit()

    def buscar_por_id(self, id_documento: str) -> Documento | None:
        with Session(self._engine) as sessao:
            registro = sessao.get(ModeloDocumento, id_documento)
            if registro is None:
                return None
            return self._mapear_para_dominio(registro)

    def listar(self) -> list[Documento]:
        with Session(self._engine) as sessao:
            stmt = select(ModeloDocumento).order_by(ModeloDocumento.titulo)
            registros = sessao.scalars(stmt).all()
            return [self._mapear_para_dominio(r) for r in registros]

    def existe(self, id_documento: str) -> bool:
        with Session(self._engine) as sessao:
            return sessao.get(ModeloDocumento, id_documento) is not None

    @classmethod
    def _mapear_para_dominio(cls, registro: ModeloDocumento) -> Documento:
        configuracao = (
            json.loads(registro.proveniencia.configuracao)
            if registro.proveniencia.configuracao
            else None
        )
        proveniencia = ProvenienciaDocumento(
            uri_origem=registro.proveniencia.uri_origem,
            metodo_extracao=registro.proveniencia.metodo_extracao,
            versao_pipeline=registro.proveniencia.versao_pipeline,
            modelo=registro.proveniencia.modelo,
            configuracao=configuracao,
            prompt=registro.proveniencia.prompt,
            executado_em=registro.proveniencia.executado_em,
        )

        paginas: list[PaginaDocumento] = []
        for p in sorted(registro.paginas, key=lambda x: x.numero):
            unidades: list[UnidadeDocumento] = []
            for u in sorted(p.unidades, key=lambda x: x.ordem_leitura):
                caixa = None
                if (
                    u.x0 is not None
                    and u.y0 is not None
                    and u.x1 is not None
                    and u.y1 is not None
                ):
                    caixa = CaixaDelimitadora(u.x0, u.y0, u.x1, u.y1)
                evidencias = json.loads(u.ids_evidencias) if u.ids_evidencias else []
                unidades.append(
                    UnidadeDocumento(
                        id_unidade=u.id,
                        id_documento=u.documento_id,
                        id_pagina=u.pagina_id,
                        tipo=u.tipo,
                        texto=u.texto,
                        ordem_leitura=u.ordem_leitura,
                        caixa=caixa,
                        fonte=u.fonte,
                        ids_evidencias=evidencias,
                        eh_decorativa=u.eh_decorativa,
                    )
                )
            paginas.append(
                PaginaDocumento(
                    id_pagina=p.id,
                    numero_pagina=p.numero,
                    texto_nativo=p.texto_nativo,
                    texto_normalizado=p.texto_normalizado,
                    metodo_extracao=p.metodo_extracao,
                    unidades=unidades,
                )
            )

        return Documento(
            id_documento=registro.id,
            uri_origem=registro.uri_origem,
            titulo=registro.titulo,
            paginas=paginas,
            versao_processamento=registro.versao_processamento,
            proveniencia=proveniencia,
        )
