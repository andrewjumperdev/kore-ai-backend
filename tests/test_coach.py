"""Coach Agent: la frontera entre "configurar al cliente" y "responder una duda".

El mismo agente se invoca desde dos lugares y solo uno debe tener efectos:

* ``POST /onboarding/diagnose`` manda ``answers`` → configura.
* El chat de ARIA en el dashboard manda solo ``message`` → responde y nada más.

Antes esa distinción no existía y un "hola" en el chat pisaba el perfil del
negocio, los módulos y la fecha de diagnóstico — o sea, borraba exactamente lo
que el cliente pagó en el setup fee. Estos tests fijan la frontera.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.coach import AgentCoach

NICHE_DEFAULTS = ["sdr", "qualification", "followup"]


@pytest.fixture
def coach():
    return AgentCoach()


def ctx(**payload):
    return SimpleNamespace(
        input=payload,
        niche_config={"default_modules": list(NICHE_DEFAULTS)},
    )


# ── Consulta (chat de ARIA) — NO debe tener efectos ─────────────────

def test_una_charla_no_habilita_modulos(coach):
    """`modules_to_enable` vacío es lo que impide que el runner pise la config:
    su side-effect está detrás de `if result.modules_to_enable`."""
    res = coach.shape_result(ctx(message="hola, todo bien?"), {"reply": "¡Hola!"})
    assert res.modules_to_enable == []


def test_una_charla_no_escribe_el_perfil_del_negocio(coach):
    """Sin facts no hay nada que sedimentar: ni en el tenant ni en la memoria
    de largo plazo."""
    res = coach.shape_result(ctx(message="hola"), {"reply": "¡Hola!"})
    assert res.facts == {}


def test_una_charla_igual_responde(coach):
    res = coach.shape_result(ctx(message="¿qué hace el módulo de seguimiento?"),
                             {"reply": "Reintenta el contacto a los N días."})
    assert res.reply == "Reintenta el contacto a los N días."


def test_el_modelo_no_puede_forzar_un_diagnostico_desde_el_chat(coach):
    """Aunque el LLM afirme `diagnosis_complete: true` y proponga módulos, sin
    `answers` sigue siendo una consulta. La señal autoritativa es el payload,
    no el texto que devuelve el modelo."""
    res = coach.shape_result(
        ctx(message="hola"),
        {"diagnosis_complete": True, "enable_modules": ["sdr", "proposal"],
         "industry": "inventada", "summary": "x"},
    )
    assert res.modules_to_enable == []
    assert res.facts == {}


def test_el_default_ausente_tampoco_configura(coach):
    """El bug original: sin `diagnosis_complete` en la respuesta, el default era
    True y cualquier mensaje configuraba al cliente."""
    res = coach.shape_result(ctx(message="gracias!"), {})
    assert res.modules_to_enable == []


# ── Diagnóstico real (onboarding) — SÍ configura ────────────────────

def test_el_diagnostico_habilita_los_modulos_que_eligio_el_coach(coach):
    res = coach.shape_result(
        ctx(message="...", answers={"¿A qué te dedicás?": "inmobiliaria en Palermo"}),
        {"summary": "Inmobiliaria residencial", "enable_modules": ["sdr", "qualification"]},
    )
    assert res.modules_to_enable == ["sdr", "qualification"]


def test_el_diagnostico_guarda_el_perfil_del_negocio(coach):
    data = {"industry": "inmobiliaria", "icp": {"description": "dueños"}, "summary": "ok"}
    res = coach.shape_result(ctx(message="...", answers={"q": "a"}), data)
    assert res.facts["business_profile"] == data


def test_si_el_coach_no_elige_modulos_caen_los_del_nicho(coach):
    """Un diagnóstico completo nunca puede dejar al cliente con cero módulos:
    quedaría trabado en el onboarding con el sistema apagado."""
    res = coach.shape_result(ctx(message="...", answers={"q": "a"}), {"summary": "ok"})
    assert res.modules_to_enable == NICHE_DEFAULTS


def test_el_diagnostico_configura_aunque_el_modelo_diga_que_no(coach):
    """Con las respuestas en la mano el diagnóstico está completo por
    definición; un `false` del modelo dejaría al cliente trabado."""
    res = coach.shape_result(
        ctx(message="...", answers={"q": "a"}),
        {"summary": "ok", "diagnosis_complete": False},
    )
    assert res.modules_to_enable == NICHE_DEFAULTS


def test_answers_vacio_no_cuenta_como_diagnostico(coach):
    """Un dict vacío es "no respondió nada", no "respondió"."""
    res = coach.shape_result(ctx(message="hola", answers={}), {"summary": "x"})
    assert res.modules_to_enable == []


# ── Rehacer el diagnóstico ──────────────────────────────────────────

class _StubSession:
    """Sesión mínima: `get` devuelve el tenant y `flush` no hace nada."""

    def __init__(self, tenant):
        self.tenant = tenant

    async def get(self, _model, _pk):
        return self.tenant

    async def scalars(self, _stmt):
        return []

    async def flush(self):
        pass


async def test_el_reset_deja_al_cliente_listo_para_rehacer(monkeypatch):
    """Sin esto el cliente quedaba en un callejón sin salida: `select_niche`
    bloquea el cambio de nicho mientras haya diagnóstico, y no existía forma de
    borrarlo."""
    from datetime import datetime, timezone

    from app.api.v1 import onboarding
    from app.models.tenant import Tenant

    tenant = Tenant(name="Cliente", slug="cliente")
    tenant.diagnosis_completed_at = datetime.now(timezone.utc)
    tenant.business_profile = {"industry": "algo que quedó mal"}
    tenant.enabled_modules = ["sdr", "qualification"]

    async def fake_info(_session, t):
        return t

    monkeypatch.setattr(onboarding, "_build_info", fake_info)
    await onboarding.reset_diagnosis(tenant_id=tenant.id, session=_StubSession(tenant))

    # El gate de select_niche mira esta fecha: en None, el nicho vuelve a ser editable.
    assert tenant.diagnosis_completed_at is None
    assert tenant.business_profile == {}
    # Módulos vacíos = los agentes dejan de operar hasta rehacer el diagnóstico.
    # Es deliberado: seguir con una config que el cliente acaba de invalidar es
    # peor que parar.
    assert tenant.enabled_modules == []
