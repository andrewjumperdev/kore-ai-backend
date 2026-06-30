from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Prospect(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Un prospecto para cold email (lista de prospección). El agente icebreaker
    genera un email personalizado a partir de su web y se envía por SMTP."""

    __tablename__ = "prospects"
    __table_args__ = (Index("ix_prospects_tenant_status", "tenant_id", "status"),)

    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    web: Mapped[str | None] = mapped_column(String(512), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # pending | sent | failed | skipped
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    subject: Mapped[str | None] = mapped_column(String(512), nullable=True)
    html: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
