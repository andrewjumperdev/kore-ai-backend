from __future__ import annotations

from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Temperature
from app.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Lead(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """A raw inbound prospect (Capa 01 output). Linked to a Contact on intake.
    The SDR Agent assigns the *initial* temperature; the Qualification Agent
    sets the definitive one."""

    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_tenant_status", "tenant_id", "status"),
    )

    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    # Channel of origin (Capa 01): whatsapp | form | landing | dm | plaud | email
    source: Mapped[str] = mapped_column(String(64), default="api", nullable=False)
    channel: Mapped[str] = mapped_column(String(32), default="whatsapp", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False)
    temperature: Mapped[str] = mapped_column(
        String(8), default=Temperature.UNSET, nullable=False
    )

    attributes: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
