"""Freno de emergencia: poder callar al agente.

Es la garantía más importante del producto para un cliente: una IA que le habla
sola a SUS clientes tiene que poder apagarse en el acto. El guard vive en
``policy.check_pre_run``, que el runner llama antes de CADA corrida, así que
cubre los tres caminos por igual — la respuesta de WhatsApp, las cadenas
disparadas por eventos y el POST manual a /agents/run.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.exceptions import PolicyViolation
from app.models.contact import Contact
from app.models.tenant import Tenant
from app.orchestrator import policy


def make_tenant(**overrides) -> Tenant:
    t = Tenant(name="Cliente", slug="cliente", niche_id=uuid4())
    t.id = uuid4()
    t.is_active = overrides.pop("is_active", True)
    t.enabled_modules = overrides.pop("enabled_modules", ["customer_service", "sdr"])
    t.diagnosis_completed_at = overrides.pop("diagnosis_completed_at", datetime.now(timezone.utc))
    t.business_profile = {}
    for k, v in overrides.items():
        setattr(t, k, v)
    return t


def make_contact(paused_until=None) -> Contact:
    c = Contact(tenant_id=uuid4(), identity_key="+5491100000000")
    c.id = uuid4()
    c.paused_until = paused_until
    c.temperature = "warm"
    return c


# ── Switch global de la cuenta ──────────────────────────────────────

def test_cuenta_activa_deja_correr():
    policy.check_pre_run("customer_service", make_tenant(), None)


def test_cuenta_apagada_frena_al_agente():
    with pytest.raises(PolicyViolation, match="pausada"):
        policy.check_pre_run("customer_service", make_tenant(is_active=False), None)


@pytest.mark.parametrize("agent", ["customer_service", "sdr", "coach", "followup"])
def test_la_cuenta_apagada_frena_a_TODOS_los_agentes(agent):
    """Incluso al Coach, que está exento de otras reglas: apagado es apagado."""
    with pytest.raises(PolicyViolation):
        policy.check_pre_run(agent, make_tenant(is_active=False), None)


def test_el_switch_global_gana_sobre_cualquier_otra_regla():
    """Un tenant apagado Y sin nicho falla por estar apagado, no por el nicho.
    El orden importa: es el motivo que hay que mostrarle al operador."""
    tenant = make_tenant(is_active=False)
    tenant.niche_id = None
    with pytest.raises(PolicyViolation, match="pausada"):
        policy.check_pre_run("customer_service", tenant, None)


# ── Pausa por conversación ──────────────────────────────────────────

def test_contacto_sin_pausa_deja_correr():
    policy.check_pre_run("customer_service", make_tenant(), make_contact())


def test_contacto_pausado_frena_al_agente():
    futuro = datetime.now(timezone.utc) + timedelta(hours=2)
    with pytest.raises(PolicyViolation, match="pausada"):
        policy.check_pre_run("customer_service", make_tenant(), make_contact(futuro))


def test_la_pausa_vencida_devuelve_el_control_al_agente():
    """La pausa tiene vencimiento a propósito: una que hay que acordarse de
    levantar termina siendo un contacto abandonado en silencio."""
    pasado = datetime.now(timezone.utc) - timedelta(minutes=1)
    policy.check_pre_run("customer_service", make_tenant(), make_contact(pasado))


def test_pausa_guardada_sin_zona_horaria_no_rompe():
    """Filas viejas pueden tener el datetime sin tz; compararlo con uno aware
    lanzaría TypeError y el agente respondería igual — justo lo contrario de
    lo que se pidió."""
    futuro_naive = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(tzinfo=None)
    with pytest.raises(PolicyViolation, match="pausada"):
        policy.check_pre_run("customer_service", make_tenant(), make_contact(futuro_naive))


def test_la_pausa_es_por_contacto_no_por_cuenta():
    """Pausar una charla no puede dejar mudo al resto del pipeline."""
    tenant = make_tenant()
    pausado = make_contact(datetime.now(timezone.utc) + timedelta(hours=1))
    otro = make_contact()

    with pytest.raises(PolicyViolation):
        policy.check_pre_run("customer_service", tenant, pausado)
    policy.check_pre_run("customer_service", tenant, otro)
