from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ModeloAlinhamento(Base):
    __tablename__ = "alinhamentos"
    __table_args__ = (
        UniqueConstraint(
            "intervalo_id",
            "documento_id",
            "estrategia",
            "origem",
            name="uq_alinhamento_intervalo_doc_est_orig",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    aula_id: Mapped[str] = mapped_column(
        ForeignKey("aulas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    documento_id: Mapped[str] = mapped_column(
        ForeignKey("documentos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    intervalo_id: Mapped[str] = mapped_column(
        ForeignKey("intervalos_explicativos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="aligned")
    tipo_relacao: Mapped[str | None] = mapped_column(String(30))
    confianca: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    estrategia: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    versao_processamento: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0")
    justificativa: Mapped[str | None] = mapped_column(Text)
    origem: Mapped[str] = mapped_column(String(20), nullable=False, default="automatic")
    ids_evidencias_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    paginas_relacionadas: Mapped[list["ModeloAlinhamentoPagina"]] = relationship(
        back_populates="alinhamento",
        cascade="all, delete-orphan",
        order_by="ModeloAlinhamentoPagina.ordem",
    )
    unidades_relacionadas: Mapped[list["ModeloAlinhamentoUnidade"]] = relationship(
        back_populates="alinhamento",
        cascade="all, delete-orphan",
        order_by="ModeloAlinhamentoUnidade.ordem",
    )


class ModeloAlinhamentoPagina(Base):
    __tablename__ = "alinhamento_paginas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alinhamento_id: Mapped[str] = mapped_column(
        ForeignKey("alinhamentos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pagina_id: Mapped[str] = mapped_column(
        ForeignKey("paginas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    alinhamento: Mapped[ModeloAlinhamento] = relationship(back_populates="paginas_relacionadas")


class ModeloAlinhamentoUnidade(Base):
    __tablename__ = "alinhamento_unidades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alinhamento_id: Mapped[str] = mapped_column(
        ForeignKey("alinhamentos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unidade_id: Mapped[str] = mapped_column(
        ForeignKey("unidades.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    alinhamento: Mapped[ModeloAlinhamento] = relationship(back_populates="unidades_relacionadas")
