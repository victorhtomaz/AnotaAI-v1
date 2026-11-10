from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ModeloAnotacao(Base):
    __tablename__ = "anotacoes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    aula_id: Mapped[str] = mapped_column(
        ForeignKey("aulas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    documento_id: Mapped[str] = mapped_column(
        ForeignKey("documentos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    intervalo_id: Mapped[str | None] = mapped_column(
        ForeignKey("intervalos_explicativos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    inicio: Mapped[float] = mapped_column(Float, nullable=False)
    fim: Mapped[float] = mapped_column(Float, nullable=False)
    tipo_relacao: Mapped[str | None] = mapped_column(String(30))
    notas: Mapped[str | None] = mapped_column(Text)
    versao: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0")

    paginas_relacionadas: Mapped[list["ModeloAnotacaoPagina"]] = relationship(
        back_populates="anotacao",
        cascade="all, delete-orphan",
        order_by="ModeloAnotacaoPagina.ordem",
    )
    unidades_relacionadas: Mapped[list["ModeloAnotacaoUnidade"]] = relationship(
        back_populates="anotacao",
        cascade="all, delete-orphan",
        order_by="ModeloAnotacaoUnidade.ordem",
    )


class ModeloAnotacaoPagina(Base):
    __tablename__ = "anotacao_paginas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anotacao_id: Mapped[str] = mapped_column(
        ForeignKey("anotacoes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pagina_id: Mapped[str] = mapped_column(
        ForeignKey("paginas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    anotacao: Mapped[ModeloAnotacao] = relationship(back_populates="paginas_relacionadas")


class ModeloAnotacaoUnidade(Base):
    __tablename__ = "anotacao_unidades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anotacao_id: Mapped[str] = mapped_column(
        ForeignKey("anotacoes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unidade_id: Mapped[str] = mapped_column(
        ForeignKey("unidades.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    anotacao: Mapped[ModeloAnotacao] = relationship(back_populates="unidades_relacionadas")
