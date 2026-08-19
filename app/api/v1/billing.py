"""Facturación (§08): setup fee + MRR.

Separación de poderes deliberada:

* ``GET /summary`` — el tenant lee su propio estado (API key de tenant).
* ``/admin/*`` — crear el plan y marcar el setup como pagado son operaciones de
  **operador**, no del cliente. Antes vivían bajo la auth del tenant, o sea que
  un cliente podía declararse pagado con su propia API key.
* ``/webhooks/stripe`` — la fuente de verdad del dinero. Stripe firma el cuerpo
  crudo; verificamos la firma antes de tocar nada.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, status

from app.api.deps import AdminAuth, DbSession, TenantId
from app.billing.engine import BillingEngine
from app.billing.stripe_client import stripe_client
from app.core.logging import get_logger
from app.core.redis import redis_client
from app.schemas.billing import (
    AdminSubscriptionCreate,
    BillingSummaryOut,
    TenantRef,
)

router = APIRouter()
log = get_logger("billing.api")


@router.get("/summary", response_model=BillingSummaryOut)
async def billing_summary(tenant_id: TenantId, session: DbSession) -> BillingSummaryOut:
    """Estado de facturación del tenant autenticado (solo lectura)."""
    return BillingSummaryOut(**await BillingEngine(session).summary(tenant_id))


# ── Operador ────────────────────────────────────────────────────────

@router.post(
    "/admin/subscription",
    response_model=BillingSummaryOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[AdminAuth],
)
async def create_subscription(
    body: AdminSubscriptionCreate, session: DbSession
) -> BillingSummaryOut:
    """Da de alta el plan de un cliente: setup fee único + MRR mensual (§08)."""
    engine = BillingEngine(session)
    await engine.create_subscription(
        body.tenant_id,
        plan=body.plan,
        setup_fee_cents=body.setup_fee_cents,
        mrr_cents=body.mrr_cents,
    )
    return BillingSummaryOut(**await engine.summary(body.tenant_id))


@router.post("/admin/setup/paid", response_model=BillingSummaryOut, dependencies=[AdminAuth])
async def mark_setup_paid(body: TenantRef, session: DbSession) -> BillingSummaryOut:
    """Marca el setup como cobrado → deal cerrado → dispara el Onboarding Agent.

    Vía de escape manual (transferencia, efectivo). El camino normal es el
    webhook de Stripe.
    """
    engine = BillingEngine(session)
    await engine.mark_setup_paid(body.tenant_id)
    return BillingSummaryOut(**await engine.summary(body.tenant_id))


# ── Stripe ──────────────────────────────────────────────────────────

async def _claim_event(event_id: str) -> bool:
    """Reclama un evento de Stripe una sola vez (dedup en Redis, TTL 7 días).

    Stripe reentrega ante cualquier duda de red. La lógica de dominio ya es
    idempotente, pero esto evita el trabajo repetido y los logs confusos.
    Si Redis no está, dejamos pasar: mejor procesar dos veces que perder un pago.
    """
    if not event_id:
        return True
    try:
        claimed = await redis_client.set(f"stripe:event:{event_id}", "1", ex=604800, nx=True)
    except Exception as exc:
        log.warning("stripe.dedup_unavailable", error=str(exc))
        return True
    return bool(claimed)


def _tenant_from_event(obj: dict) -> UUID | None:
    """El tenant viaja en la metadata del objeto de Stripe.

    Al crear el customer/checkout hay que setear ``metadata.tenant_id``; sin eso
    no hay forma de saber a quién acreditar el pago.
    """
    meta = obj.get("metadata") or {}
    raw = meta.get("tenant_id") or meta.get("kore_tenant_id")
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


@router.post("/webhooks/stripe", include_in_schema=False)
async def stripe_webhook(request: Request, session: DbSession) -> dict:
    """Eventos de pago de Stripe.

    Devolvemos 200 en los eventos que no nos interesan o que no traen tenant:
    un no-2xx hace que Stripe reintente el mismo evento durante días.
    """
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    event = stripe_client.verify_webhook(payload, signature)  # lanza si no valida

    if not await _claim_event(str(event.get("id", ""))):
        return {"received": True, "ignored": "duplicado"}

    event_type = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}
    tenant_id = _tenant_from_event(obj)
    log.info("stripe.event", type=event_type, tenant_id=str(tenant_id) if tenant_id else None)

    if tenant_id is None:
        return {"received": True, "ignored": "sin tenant_id en metadata"}

    engine = BillingEngine(session)

    if event_type in ("checkout.session.completed", "invoice.paid", "invoice.payment_succeeded"):
        summary = await engine.summary(tenant_id)
        # El primer pago cierra el deal; los siguientes son el ciclo mensual.
        if not summary.get("setup_paid"):
            await engine.mark_setup_paid(tenant_id)
        else:
            await engine.open_period_invoice(tenant_id)
    elif event_type in ("customer.subscription.deleted", "subscription_schedule.canceled"):
        await engine.cancel_subscription(tenant_id)
    elif event_type == "invoice.payment_failed":
        await engine.mark_past_due(tenant_id)
    else:
        return {"received": True, "ignored": event_type}

    return {"received": True, "handled": event_type}
