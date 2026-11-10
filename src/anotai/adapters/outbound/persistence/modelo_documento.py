from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ModeloDocumento(Base):
    __tablename__ = "documentos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    uri_origem: Mapped[str] = mapped_column(Text, nullable=False)
    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    versao_processamento: Mapped[str] = mapped_column(String(100), nullable=False)
    paginas: Mapped[list["ModeloPagina"]] = relationship(
        back_populates="documento", cascade="all, delete-orphan"
    )
    proveniencia: Mapped["ModeloProveniencia"] = relationship(
        back_populates="documento", cascade="all, delete-orphan", uselist=False
    )


class ModeloPagina(Base):
    __tablename__ = "paginas"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    documento_id: Mapped[str] = mapped_column(
        ForeignKey("documentos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    texto_nativo: Mapped[str] = mapped_column(Text, nullable=False)
    texto_normalizado: Mapped[str] = mapped_column(Text, nullable=False)
    metodo_extracao: Mapped[str] = mapped_column(String(30), nullable=False)
    documento: Mapped[ModeloDocumento] = relationship(back_populates="paginas")
    unidades: Mapped[list["ModeloUnidade"]] = relationship(
        back_populates="pagina", cascade="all, delete-orphan"
    )


class ModeloUnidade(Base):
    __tablename__ = "unidades"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    documento_id: Mapped[str] = mapped_column(
        ForeignKey("documentos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pagina_id: Mapped[str] = mapped_column(
        ForeignKey("paginas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    texto: Mapped[str | None] = mapped_column(Text)
    ordem_leitura: Mapped[int] = mapped_column(Integer, nullable=False)
    x0: Mapped[float | None] = mapped_column()
    y0: Mapped[float | None] = mapped_column()
    x1: Mapped[float | None] = mapped_column()
    y1: Mapped[float | None] = mapped_column()
    fonte: Mapped[str] = mapped_column(String(30), nullable=False)
    ids_evidencias: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    eh_decorativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pagina: Mapped[ModeloPagina] = relationship(back_populates="unidades")


class ModeloProveniencia(Base):
    __tablename__ = "proveniencias"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    documento_id: Mapped[str] = mapped_column(
        ForeignKey("documentos.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    uri_origem: Mapped[str] = mapped_column(Text, nullable=False)
    metodo_extracao: Mapped[str] = mapped_column(String(30), nullable=False)
    versao_pipeline: Mapped[str] = mapped_column(String(100), nullable=False)
    modelo: Mapped[str | None] = mapped_column(String(200))
    configuracao: Mapped[str | None] = mapped_column(Text)
    prompt: Mapped[str | None] = mapped_column(Text)
    executado_em: Mapped[str | None] = mapped_column(String(50))
    documento: Mapped[ModeloDocumento] = relationship(back_populates="proveniencia")
