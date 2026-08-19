"""ARIA, el asistente del panel.

Existe separado del Coach por una razón concreta: el Coach configura al cliente
y ARIA no debe poder hacerlo *ni por accidente ni a pedido del modelo*. Estos
tests fijan esa incapacidad estructural y el hilo de conversación propio.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.agents.assistant import AssistantAgent
from app.api.v1.assistant import aria_thread_id
from app.orchestrator import policy


@pytest.fixture
def aria():
    return AssistantAgent()


def ctx(**payload):
    return SimpleNamespace(input=payload, niche_config={})


# ── No puede configurar nada ────────────────────────────────────────

def test_nunca_habilita_modulos(aria):
    """`modules_to_enable` vacío es lo que mantiene cerrado el side-effect del
    runner, que está detrás de `if result.modules_to_enable`."""
    res = aria.shape_result(ctx(message="hola"), {"reply": "¡Hola!"})
    assert res.modules_to_enable == []


def test_nunca_escribe_el_perfil_del_negocio(aria):
    res = aria.shape_result(ctx(message="hola"), {"reply": "¡Hola!"})
    assert res.facts == {}


def test_ignora_al_modelo_si_intenta_configurar(aria):
    """Aunque el LLM devuelva módulos y perfil —por prompt injection o por
    alucinación— el agente los descarta: no los lee siquiera."""
    res = aria.shape_result(
        ctx(message="activá todos los módulos"),
        {
            "reply": "Listo",
            "enable_modules": ["sdr", "proposal", "content"],
            "diagnosis_complete": True,
            "industry": "lo que sea",
        },
    )
    assert res.modules_to_enable == []
    assert res.facts == {}


def test_responde(aria):
    res = aria.shape_result(ctx(message="¿qué es la cola humana?"),
                            {"reply": "Lo que los agentes dejaron para que apruebes vos."})
    assert res.reply == "Lo que los agentes dejaron para que apruebes vos."


def test_tolera_que_el_modelo_use_summary(aria):
    """Los otros agentes de la cadena devuelven `summary`; si el modelo cae en
    ese hábito, no queremos una burbuja vacía."""
    res = aria.shape_result(ctx(message="hola"), {"summary": "Todo en orden."})
    assert res.reply == "Todo en orden."


def test_sin_texto_devuelve_cadena_vacia_no_none(aria):
    """`reply=None` rompería el contrato de respuesta del endpoint."""
    assert aria.shape_result(ctx(message="hola"), {}).reply == ""


# ── Funciona desde el minuto cero ───────────────────────────────────

def test_no_requiere_nicho():
    """Alguien recién registrado, antes de elegir rubro, tiene que poder
    preguntar. El Coach sí exige nicho; ARIA no."""
    assert "assistant" in policy.NICHE_EXEMPT


def test_no_depende_de_ningun_modulo():
    """Si estuviera atado a un módulo, quedaría muda hasta que el Coach los
    habilite — justo cuando más preguntas hay."""
    assert "assistant" not in policy.AGENT_MODULE


# ── Hilo de conversación ────────────────────────────────────────────

def test_el_hilo_es_estable_para_el_mismo_tenant():
    """Si cambiara entre requests, ARIA perdería la memoria en cada mensaje."""
    tid = uuid.uuid4()
    assert aria_thread_id(tid) == aria_thread_id(tid)


def test_cada_tenant_tiene_su_propio_hilo():
    """Compartir hilo filtraría la conversación de un cliente a otro."""
    assert aria_thread_id(uuid.uuid4()) != aria_thread_id(uuid.uuid4())


def test_el_hilo_no_colisiona_con_el_id_del_tenant():
    """Se deriva, no se reusa: un id de conversación igual al del tenant
    invitaría a confundir las dos cosas."""
    tid = uuid.uuid4()
    assert aria_thread_id(tid) != tid
