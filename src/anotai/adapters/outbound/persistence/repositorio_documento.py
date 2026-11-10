import json
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from anotai.domain.entities.Documento import Documento

from .base import Base
from .modelo_documento import (
    ModeloDocumento,
    ModeloPagina,
    ModeloProveniencia,
    ModeloUnidade,
)


class RepositorioDocumento:
    def __init__(self, caminho_banco: Path) -> None:
        caminho_banco.parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{caminho_banco}", future=True)
        self.caminho_banco = caminho_banco
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
                    configuracao=json.dumps(documento.proveniencia.configuracao),
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

    def existe(self, documento_id: str) -> bool:
        with Session(self._engine) as sessao:
            return sessao.get(ModeloDocumento, documento_id) is not None
