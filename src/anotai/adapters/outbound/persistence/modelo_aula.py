from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ModeloAula(Base):
    __tablename__ = "aulas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    uri_origem: Mapped[str] = mapped_column(Text, nullable=False)
    duracao: Mapped[float] = mapped_column(Float, nullable=False)
    taxa_amostragem: Mapped[int] = mapped_column(Integer, nullable=False)
    canais: Mapped[int] = mapped_column(Integer, nullable=False)
    formato: Mapped[str] = mapped_column(String(30), nullable=False)
    codec: Mapped[str | None] = mapped_column(String(50))
    taxa_bits: Mapped[int | None] = mapped_column(Integer)
    idioma: Mapped[str | None] = mapped_column(String(20))
    versao_processamento: Mapped[str] = mapped_column(String(50), default="1.0")
    carga_bruta_asr: Mapped[str | None] = mapped_column(Text)

    segmentos: Mapped[list["ModeloSegmentoTranscricao"]] = relationship(
        back_populates="aula",
        cascade="all, delete-orphan",
        order_by="ModeloSegmentoTranscricao.ordem",
    )
    intervalos: Mapped[list["ModeloIntervaloExplicativo"]] = relationship(
        back_populates="aula",
        cascade="all, delete-orphan",
        order_by="ModeloIntervaloExplicativo.ordem",
    )


class ModeloSegmentoTranscricao(Base):
    __tablename__ = "segmentos_transcricao"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    aula_id: Mapped[str] = mapped_column(
        ForeignKey("aulas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    inicio: Mapped[float] = mapped_column(Float, nullable=False)
    fim: Mapped[float] = mapped_column(Float, nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    fonte: Mapped[str] = mapped_column(String(30), nullable=False, default="asr")
    confianca: Mapped[float | None] = mapped_column(Float)
    palavras_json: Mapped[str | None] = mapped_column(Text)

    aula: Mapped[ModeloAula] = relationship(back_populates="segmentos")


class ModeloIntervaloExplicativo(Base):
    __tablename__ = "intervalos_explicativos"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    aula_id: Mapped[str] = mapped_column(
        ForeignKey("aulas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    inicio: Mapped[float] = mapped_column(Float, nullable=False)
    fim: Mapped[float] = mapped_column(Float, nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False, default="explanation")
    notas: Mapped[str | None] = mapped_column(Text)
    ids_segmentos_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    aula: Mapped[ModeloAula] = relationship(back_populates="intervalos")
