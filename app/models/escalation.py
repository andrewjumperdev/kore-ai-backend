from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import EscalationStatus
from app.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Escalation(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """A human-in-the-loop handoff (P3). Agents prepare and escalate; they do
    NOT close deals, approve budgets, or publish authority content alone. Each
    escalation carries an executive summary for Silvana/Andrew."""

    __tablename__ = "escalations"
    __table_args__ = (
        Index("ix_escalations_tenant_status", "tenant_id", "status"),
    )

    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=EscalationStatus.OPEN, nullable=False
    )
    source_agent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    executive_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Recommended next action + any prepared artifact (proposal, content draft…).
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
