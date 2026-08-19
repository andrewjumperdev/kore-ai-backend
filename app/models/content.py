"""Piezas de contenido generadas por el Content Agent (Capa 03).

El agente ya generaba, pero nada se guardaba: el banco y el calendario vivían en
el estado del navegador y se perdían al refrescar. Una pieza que costó una
llamada al LLM y que la persona aprobó tiene que sobrevivir a un F5.

`status` distingue lo generado de lo publicado: el agente PREPARA y una persona
decide (P3). Nada se publica solo.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ContentPiece(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "content_pieces"

    # reel | carrusel | historia | post
    fmt: Mapped[str] = mapped_column("format", String(16), nullable=False)
    # autoridad | conversion | confianza | atraccion
    pillar: Mapped[str] = mapped_column(String(16), nullable=False)

    # El pedido con el que se generó, para poder repetir o afinar después.
    context: Mapped[str] = mapped_column(Text, default="", nullable=False)
    zona: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # draft | scheduled | published
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
