"""Billing engine — setup fee + monthly recurring subscription (MRR), per §08.

Lifecycle:
  create_subscription  → trialing + an OPEN setup invoice
  mark_setup_paid      → setup paid → DEAL_CLOSED (triggers Onboarding Agent)
  open_period_invoice  → one subscription invoice per period (idempotent)
  cancel_subscription  → canceled (feeds churn metric)

No contact metering — KORE IA monetizes setup + suscripción.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.events.bus import event_bus
from app.events.types import EventName
from app.models.billing import Invoice, Subscription

log = get_logger("billing")


def _period_key(at: datetime) -> str:
    return at.strftime("%Y-%m")


class BillingEngine:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def subscription(self, tenant_id: UUID) -> Subscription | None:
        return await self.session.scalar(
            select(Subscription).where(Subscription.tenant_id == tenant_id)
        )

    async def create_subscription(
        self,
        tenant_id: UUID,
        *,
        plan: str,
        setup_fee_cents: int,
        mrr_cents: int,
    ) -> Subscription:
        sub = Subscription(
            tenant_id=tenant_id,
            plan=plan,
            status="trialing",
            setup_fee_cents=setup_fee_cents,
            mrr_cents=mrr_cents,
        )
        self.session.add(sub)
        if setup_fee_cents > 0:
            self.session.add(
                Invoice(
                    tenant_id=tenant_id,
                    kind="setup",
                    amount_cents=setup_fee_cents,
                    status="open",
                )
            )
        await self.session.flush()
        await event_bus.emit(
            self.session,
            EventName.SUBSCRIPTION_UPDATED,
            source="billing",
            payload={"plan": plan, "mrr_cents": mrr_cents, "status": "trialing"},
            tenant_id=tenant_id,
        )
        return sub

    async def mark_setup_paid(self, tenant_id: UUID, at: datetime | None = None) -> Subscription:
        """Client paid setup → deal is closed. Activates the recurring period and
        emits DEAL_CLOSED so the Onboarding Agent kicks in (§05)."""
        at = at or datetime.now(timezone.utc)
        sub = await self.subscription(tenant_id)
        if sub is None:
            raise NotFoundError("No subscription for tenant")
        sub.setup_paid_at = at
        sub.status = "active"
        sub.started_at = at
        sub.current_period_start = at
        sub.current_period_end = at + timedelta(days=30)

        setup_invoice = await self.session.scalar(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id,
                Invoice.kind == "setup",
                Invoice.status == "open",
            )
        )
        if setup_invoice:
            setup_invoice.status = "paid"
            setup_invoice.paid_at = at

        await event_bus.emit(
            self.session, EventName.SETUP_PAID, source="billing",
            payload={"amount_cents": sub.setup_fee_cents}, tenant_id=tenant_id,
        )
        await event_bus.emit(
            self.session, EventName.DEAL_CLOSED, source="billing",
            subject_type="tenant", subject_id=str(tenant_id),
            payload={"plan": sub.plan, "mrr_cents": sub.mrr_cents}, tenant_id=tenant_id,
        )
        log.info("billing.setup_paid", tenant_id=str(tenant_id))
        return sub

    async def open_period_invoice(self, tenant_id: UUID, at: datetime | None = None) -> Invoice | None:
        """Create the subscription invoice for the current period (idempotent
        per tenant+period via the unique-ish period_key check)."""
        at = at or datetime.now(timezone.utc)
        sub = await self.subscription(tenant_id)
        if sub is None or sub.status != "active":
            return None
        pkey = _period_key(at)
        existing = await self.session.scalar(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id,
                Invoice.kind == "subscription",
                Invoice.period_key == pkey,
            )
        )
        if existing:
            return existing
        invoice = Invoice(
            tenant_id=tenant_id,
            kind="subscription",
            amount_cents=sub.mrr_cents,
            period_key=pkey,
            status="open",
        )
        self.session.add(invoice)
        await self.session.flush()
        return invoice

    async def cancel_subscription(self, tenant_id: UUID, at: datetime | None = None) -> Subscription:
        at = at or datetime.now(timezone.utc)
        sub = await self.subscription(tenant_id)
        if sub is None:
            raise NotFoundError("No subscription for tenant")
        sub.status = "canceled"
        sub.canceled_at = at
        await event_bus.emit(
            self.session, EventName.SUBSCRIPTION_CANCELED, source="billing",
            payload={"plan": sub.plan, "mrr_cents": sub.mrr_cents}, tenant_id=tenant_id,
        )
        log.info("billing.canceled", tenant_id=str(tenant_id))
        return sub

    async def summary(self, tenant_id: UUID) -> dict:
        sub = await self.subscription(tenant_id)
        if sub is None:
            return {"plan": None, "status": "none", "mrr_cents": 0, "setup_fee_cents": 0}
        return {
            "plan": sub.plan,
            "status": sub.status,
            "mrr_cents": sub.mrr_cents,
            "setup_fee_cents": sub.setup_fee_cents,
            "setup_paid": sub.setup_paid_at is not None,
            "current_period_end": sub.current_period_end,
        }
