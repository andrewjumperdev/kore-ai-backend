from __future__ import annotations

from sqlalchemy import BigInteger, Identity, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Event(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Append-only event log. The source of truth for analytics, audit, and
    asynchronous fan-out. Partition by created_at in production (declarative
    partitioning) to keep millions of rows queryable."""

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_tenant_name_created", "tenant_id", "name", "created_at"),
    )

    # Monotonic per-row sequence for cursor pagination on the /events feed.
    # GENERATED ... AS IDENTITY so it auto-populates even though it is not the PK.
    seq: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "lead.created"
    source: Mapped[str] = mapped_column(String(48), default="system", nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # Optional correlation to a domain object for fast filtering.
    subject_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    subject_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
