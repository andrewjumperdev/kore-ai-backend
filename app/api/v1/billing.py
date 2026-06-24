from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import DbSession, TenantId
from app.billing.engine import BillingEngine
from app.schemas.billing import BillingSummaryOut, SubscriptionCreate

router = APIRouter()


@router.post("/subscription", response_model=BillingSummaryOut, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    body: SubscriptionCreate, tenant_id: TenantId, session: DbSession
) -> BillingSummaryOut:
    """Create the client's plan: one-time setup fee + monthly MRR (§08)."""
    engine = BillingEngine(session)
    await engine.create_subscription(
        tenant_id,
        plan=body.plan,
        setup_fee_cents=body.setup_fee_cents,
        mrr_cents=body.mrr_cents,
    )
    return BillingSummaryOut(**await engine.summary(tenant_id))


@router.post("/setup/paid", response_model=BillingSummaryOut)
async def mark_setup_paid(tenant_id: TenantId, session: DbSession) -> BillingSummaryOut:
    """Mark the setup fee paid → deal closed → triggers the Onboarding Agent."""
    engine = BillingEngine(session)
    await engine.mark_setup_paid(tenant_id)
    return BillingSummaryOut(**await engine.summary(tenant_id))


@router.get("/summary", response_model=BillingSummaryOut)
async def billing_summary(tenant_id: TenantId, session: DbSession) -> BillingSummaryOut:
    return BillingSummaryOut(**await BillingEngine(session).summary(tenant_id))
