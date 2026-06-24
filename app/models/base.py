"""Declarative base + reusable mixins.

TenantMixin is the isolation contract: every tenant-owned table carries an
indexed, NOT NULL ``tenant_id``. Combined with the repository layer (which
always filters by the active tenant) this gives row-level isolation without
relying on application code to remember the filter ad hoc.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TenantMixin:
    @staticmethod
    def _tenant_fk() -> Mapped[uuid.UUID]:
        return mapped_column(
            PgUUID(as_uuid=True),
            ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )

    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
