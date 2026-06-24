from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import LifecycleStage, Temperature
from app.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Contact(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """A unique person within a tenant (the CRM record / system memory, P5).

    ``identity_key`` is the canonical dedup key (normalized phone or email).
    ``temperature`` is the categorical classification owned by the Qualification
    Agent (🔴 cold / 🟡 warm / 🟢 hot). Outbound communication is gated on it
    being set (P1).
    """

    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "identity_key", name="uq_contact_identity"),
    )

    identity_key: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    lifecycle_stage: Mapped[str] = mapped_column(
        String(16), default=LifecycleStage.LEAD, nullable=False
    )
    temperature: Mapped[str] = mapped_column(
        String(8), default=Temperature.UNSET, nullable=False, index=True
    )
    # Orchestrator anti-spam counters (§05: > 4x sin avance → pausa + flag).
    contact_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    paused_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    attributes: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class ContactActivity(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "contact_activities"

    contact_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
