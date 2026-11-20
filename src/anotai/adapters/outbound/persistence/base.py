from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def criar_engine_sqlite(caminho_banco: Path) -> Engine:
    caminho_banco.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{caminho_banco}", future=True)

    @event.listens_for(engine, "connect")
    def _ativar_chaves_estrangeiras(dbapi_connection: Any, connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def inicializar_engine_sqlite(caminho_banco: Path) -> Engine:
    """Cria a engine SQLite registrando todos os modelos antes de executar create_all."""
    from . import (  # noqa: F401
        modelo_alinhamento,
        modelo_anotacao,
        modelo_aula,
        modelo_documento,
    )

    engine = criar_engine_sqlite(caminho_banco)
    Base.metadata.create_all(engine)
    return engine
