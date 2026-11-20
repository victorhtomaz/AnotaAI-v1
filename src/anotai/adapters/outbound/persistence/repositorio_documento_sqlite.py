import json
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, selectinload

from anotai.application.ports.repositorio_documento import (
    RepositorioDocumento as RepositorioDocumentoPort,
)
from anotai.domain.entities import (
    Documento,
    PaginaDocumento,
    UnidadeDocumento,
    ValidadorIntegridade,
)
from anotai.domain.value_objects import CaixaDelimitadora, ProvenienciaDocumento

from .base import inicializar_engine_sqlite
from .modelo_documento import (
    ModeloDocumento,
    ModeloPagina,
    ModeloProveniencia,
    ModeloUnidade,
)


class RepositorioDocumentoSQLite(RepositorioDocumentoPort):
    def __init__(self, caminho_banco: Path, engine: Engine | None = None) -> None:
        self.caminho_banco = caminho_banco
        self._engine = engine if engine is not None else inicializar_engine_sqlite(caminho_banco)

    def salvar(self, documento: Documento) -> None:
        ValidadorIntegridade.validar_documento(documento)

        with Session(self._engine) as sessao:
            existente = sessao.get(ModeloDocumento, documento.id_documento)
            proveniencia_model = ModeloProveniencia(
                uri_origem=documento.proveniencia.uri_origem,
                metodo_extracao=documento.proveniencia.metodo_extracao,
                versao_pipeline=documento.proveniencia.versao_pipeline,
                modelo=documento.proveniencia.modelo,
                configuracao=json.dumps(documento.proveniencia.configuracao)
                if documento.proveniencia.configuracao
                else None,
                prompt=documento.proveniencia.prompt,
                executado_em=documento.proveniencia.executado_em,
            )

            if existente is not None:
                existente.uri_origem = documento.uri_origem
                existente.titulo = documento.titulo
                existente.versao_processamento = documento.versao_processamento
                if existente.proveniencia is not None:
                    existente.proveniencia.uri_origem = documento.proveniencia.uri_origem
                    existente.proveniencia.metodo_extracao = (
                        documento.proveniencia.metodo_extracao
                    )
                    existente.proveniencia.versao_pipeline = (
                        documento.proveniencia.versao_pipeline
                    )
                    existente.proveniencia.modelo = documento.proveniencia.modelo
                    existente.proveniencia.configuracao = (
                        json.dumps(documento.proveniencia.configuracao)
                        if documento.proveniencia.configuracao
                        else None
                    )
                    existente.proveniencia.prompt = documento.proveniencia.prompt
                    existente.proveniencia.executado_em = documento.proveniencia.executado_em
                else:
                    existente.proveniencia = proveniencia_model
                existente.paginas.clear()
                registro = existente
            else:
                registro = ModeloDocumento(
                    id=documento.id_documento,
                    uri_origem=documento.uri_origem,
                    titulo=documento.titulo,
                    versao_processamento=documento.versao_processamento,
                    proveniencia=proveniencia_model,
                )
                sessao.add(registro)

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

            sessao.commit()

    def buscar_por_id(self, id_documento: str) -> Documento | None:
        with Session(self._engine) as sessao:
            stmt = (
                select(ModeloDocumento)
                .where(ModeloDocumento.id == id_documento)
                .options(
                    selectinload(ModeloDocumento.paginas).selectinload(ModeloPagina.unidades),
                    selectinload(ModeloDocumento.proveniencia),
                )
            )
            registro = sessao.scalars(stmt).first()
            if registro is None:
                return None
            return self._mapear_para_dominio(registro)

    def listar(self) -> list[Documento]:
        with Session(self._engine) as sessao:
            stmt = (
                select(ModeloDocumento)
                .options(
                    selectinload(ModeloDocumento.paginas).selectinload(ModeloPagina.unidades),
                    selectinload(ModeloDocumento.proveniencia),
                )
                .order_by(ModeloDocumento.titulo)
            )
            registros = sessao.scalars(stmt).all()
            return [self._mapear_para_dominio(r) for r in registros]

    def existe(self, id_documento: str) -> bool:
        with Session(self._engine) as sessao:
            stmt = select(1).where(ModeloDocumento.id == id_documento)
            return sessao.scalar(stmt) is not None

    def excluir(self, id_documento: str) -> bool:
        with Session(self._engine) as sessao:
            registro = sessao.get(ModeloDocumento, id_documento)
            if registro is None:
                return False
            sessao.delete(registro)
            sessao.commit()
            return True

    def buscar_por_termo(self, termo: str) -> list[tuple[str, str]]:
        termo_limpo = termo.strip()
        with Session(self._engine) as sessao:
            stmt = select(ModeloDocumento.id, ModeloDocumento.titulo).where(
                (ModeloDocumento.id.contains(termo_limpo))
                | (ModeloDocumento.titulo.ilike(f"%{termo_limpo}%"))
            )
            return [(row[0], row[1]) for row in sessao.execute(stmt)]

    @staticmethod
    def _mapear_para_dominio(registro: ModeloDocumento) -> Documento:
        paginas: list[PaginaDocumento] = []
        for reg_pag in sorted(registro.paginas, key=lambda p: p.numero):
            unidades: list[UnidadeDocumento] = []
            for reg_u in sorted(reg_pag.unidades, key=lambda u: u.ordem_leitura):
                caixa = (
                    CaixaDelimitadora(reg_u.x0, reg_u.y0, reg_u.x1, reg_u.y1)
                    if reg_u.x0 is not None
                    and reg_u.y0 is not None
                    and reg_u.x1 is not None
                    and reg_u.y1 is not None
                    else None
                )
                ids_evidencias = (
                    json.loads(reg_u.ids_evidencias) if reg_u.ids_evidencias else []
                )
                unidades.append(
                    UnidadeDocumento(
                        id_unidade=reg_u.id,
                        id_documento=reg_u.documento_id,
                        id_pagina=reg_u.pagina_id,
                        tipo=reg_u.tipo,
                        texto=reg_u.texto,
                        ordem_leitura=reg_u.ordem_leitura,
                        caixa=caixa,
                        fonte=reg_u.fonte,
                        ids_evidencias=ids_evidencias,
                        eh_decorativa=reg_u.eh_decorativa,
                    )
                )

            paginas.append(
                PaginaDocumento(
                    id_pagina=reg_pag.id,
                    numero_pagina=reg_pag.numero,
                    texto_nativo=reg_pag.texto_nativo,
                    texto_normalizado=reg_pag.texto_normalizado,
                    metodo_extracao=reg_pag.metodo_extracao,
                    unidades=unidades,
                )
            )

        reg_prov = registro.proveniencia
        configuracao = (
            json.loads(reg_prov.configuracao)
            if reg_prov and reg_prov.configuracao
            else None
        )
        proveniencia = ProvenienciaDocumento(
            uri_origem=reg_prov.uri_origem if reg_prov else registro.uri_origem,
            metodo_extracao=reg_prov.metodo_extracao if reg_prov else "native",
            versao_pipeline=reg_prov.versao_pipeline if reg_prov else "1.0",
            modelo=reg_prov.modelo if reg_prov else None,
            configuracao=configuracao,
            prompt=reg_prov.prompt if reg_prov else None,
            executado_em=reg_prov.executado_em if reg_prov else None,
        )

        return Documento(
            id_documento=registro.id,
            uri_origem=registro.uri_origem,
            titulo=registro.titulo,
            paginas=paginas,
            versao_processamento=registro.versao_processamento,
            proveniencia=proveniencia,
        )


# Alias para retrocompatibilidade
RepositorioDocumento = RepositorioDocumentoSQLite

__all__ = ["RepositorioDocumento", "RepositorioDocumentoSQLite"]
