"""Motor de facturación: setup fee + MRR.

Lo que se cuida acá es que un pago no se procese dos veces. Stripe reentrega el
mismo evento ante cualquier duda de red, y ``DEAL_CLOSED`` dispara el Onboarding
Agent: emitirlo dos veces le manda al cliente la bienvenida duplicada.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.billing.engine import BillingEngine
from app.core.exceptions import NotFoundError
from app.events.types import EventName
from app.models.billing import Subscription

TENANT = uuid4()


class FakeSession:
    """Devuelve resultados scripteados para cada `scalar` en orden."""

    def __init__(self, *results):
        self._results = list(results)
        self.added: list = []

    async def scalar(self, _stmt):
        return self._results.pop(0) if self._results else None

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


@pytest.fixture
def emitted(monkeypatch):
    """Captura los eventos emitidos en vez de tocar la base."""
    events: list[str] = []

    async def fake_emit(_session, name, **_kwargs):
        events.append(name)

    from app.events import bus

    monkeypatch.setattr(bus.event_bus, "emit", fake_emit)
    return events


def make_sub(**overrides) -> Subscription:
    sub = Subscription(
        tenant_id=TENANT,
        plan="real-estate-growth",
        status=overrides.pop("status", "trialing"),
        setup_fee_cents=overrides.pop("setup_fee_cents", 100_000),
        mrr_cents=overrides.pop("mrr_cents", 50_000),
    )
    for key, value in overrides.items():
        setattr(sub, key, value)
    return sub


async def test_marcar_setup_pagado_activa_y_cierra_el_deal(emitted):
    sub = make_sub()
    engine = BillingEngine(FakeSession(sub, None))

    result = await engine.mark_setup_paid(TENANT)

    assert result.status == "active"
    assert result.setup_paid_at is not None
    assert result.current_period_end > result.current_period_start
    assert EventName.DEAL_CLOSED in emitted
    assert EventName.SETUP_PAID in emitted


async def test_marcar_setup_pagado_es_idempotente(emitted):
    """El evento repetido de Stripe no debe re-disparar el onboarding."""
    ya_pagado = datetime(2026, 1, 5, tzinfo=timezone.utc)
    sub = make_sub(status="active", setup_paid_at=ya_pagado)
    engine = BillingEngine(FakeSession(sub, None))

    result = await engine.mark_setup_paid(TENANT)

    assert result.setup_paid_at == ya_pagado  # no se pisa la fecha original
    assert emitted == []                      # y no se emite nada de nuevo


async def test_marcar_pagado_sin_suscripcion_falla():
    engine = BillingEngine(FakeSession(None))
    with pytest.raises(NotFoundError):
        await engine.mark_setup_paid(TENANT)


async def test_pago_fallido_marca_past_due_sin_cancelar(emitted):
    """Stripe reintenta varios días; cancelar al primer fallo sería perder al cliente."""
    sub = make_sub(status="active")
    engine = BillingEngine(FakeSession(sub))

    result = await engine.mark_past_due(TENANT)

    assert result.status == "past_due"
    assert EventName.SUBSCRIPTION_UPDATED in emitted


async def test_past_due_no_revive_una_cancelada(emitted):
    sub = make_sub(status="canceled")
    engine = BillingEngine(FakeSession(sub))

    result = await engine.mark_past_due(TENANT)

    assert result.status == "canceled"
    assert emitted == []


async def test_past_due_sin_suscripcion_no_rompe():
    assert await BillingEngine(FakeSession(None)).mark_past_due(TENANT) is None


async def test_factura_del_periodo_no_se_duplica():
    """Idempotencia por período: el scheduler mensual puede correr dos veces."""
    sub = make_sub(status="active")
    existente = object()
    engine = BillingEngine(FakeSession(sub, existente))

    assert await engine.open_period_invoice(TENANT) is existente


async def test_no_factura_si_la_suscripcion_no_esta_activa():
    sub = make_sub(status="trialing")
    assert await BillingEngine(FakeSession(sub)).open_period_invoice(TENANT) is None


async def test_summary_sin_suscripcion():
    summary = await BillingEngine(FakeSession(None)).summary(TENANT)
    assert summary["status"] == "none"
    assert summary["mrr_cents"] == 0
