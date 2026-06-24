from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A client business — an instance of a Niche.

    The niche supplies the calibrated configuration; the tenant supplies the
    specific business diagnosis produced by the Coach Agent and the set of
    modules enabled for it.
    """

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Replicable model: every client belongs to a niche (P2 — niche mandatory).
    niche_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("niches.id", ondelete="RESTRICT"), index=True
    )

    # Filled by Agent Coach during diagnosis (industry, ICP, pains, offers…).
    business_profile: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # P6 gate: proposals require a completed diagnosis.
    diagnosis_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Modules enabled by the Coach Agent after diagnosis (list[Module]).
    enabled_modules: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    # Post-deal activation (Onboarding Agent).
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    api_keys: Mapped[list["TenantApiKey"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )

    @property
    def has_diagnosis(self) -> bool:
        return self.diagnosis_completed_at is not None


class TenantApiKey(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tenant_api_keys"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), default="default", nullable=False)
    hashed_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    tenant: Mapped["Tenant"] = relationship(back_populates="api_keys")
