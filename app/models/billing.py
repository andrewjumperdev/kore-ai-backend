"""Billing per §08: one-time setup fee + monthly recurring subscription (MRR).
Contact-metered usage was removed — KORE IA monetizes setup + suscripción, and
the orchestrator tracks MRR/churn as business metrics."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Subscription(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """The client's recurring plan. ``mrr_cents`` is the monthly recurring
    revenue this subscription contributes; ``status`` drives churn metrics."""

    __tablename__ = "subscriptions"

    plan: Mapped[str] = mapped_column(String(48), nullable=False)  # e.g. niche-growth
    status: Mapped[str] = mapped_column(String(16), default="trialing", nullable=False)
    # active | trialing | past_due | canceled

    setup_fee_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    setup_paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    mrr_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Invoice(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """A billed item — the one-time setup or a monthly subscription charge."""

    __tablename__ = "invoices"

    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # setup | subscription
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    # open | paid | void
    period_key: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)
    stripe_invoice_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
