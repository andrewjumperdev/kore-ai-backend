"""Billing tasks — open the monthly subscription invoice (MRR) for each active
tenant. Scheduled monthly by the scheduler process."""
from __future__ import annotations

from uuid import UUID

import dramatiq
from sqlalchemy import select

from app.billing.engine import BillingEngine
from app.core.context import tenant_context
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.billing import Subscription
from app.tasks.broker import run_async

log = get_logger("billing_tasks")


@dramatiq.actor(queue_name="billing")
def open_period_invoice(tenant_id: str) -> None:
    async def _run() -> None:
        tid = UUID(tenant_id)
        with tenant_context(tid):
            async with session_scope() as session:
                await BillingEngine(session).open_period_invoice(tid)

    run_async(_run())


@dramatiq.actor(queue_name="billing")
def open_all_period_invoices() -> None:
    async def _run() -> list[str]:
        async with session_scope() as session:
            ids = (
                await session.scalars(
                    select(Subscription.tenant_id).where(Subscription.status == "active")
                )
            ).all()
        return [str(i) for i in ids]

    for tid in run_async(_run()):
        open_period_invoice.send(tid)
    log.info("billing.invoices_dispatched")
