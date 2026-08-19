"""Envíos salientes: que salgan, y que se sepa cuando no salen.

Los dos bugs que cubre este archivo compartían la misma forma: el sistema
reportaba éxito sobre un no-op. El follow-up redactaba mensajes que el canal
descartaba, y el descarte no dejaba rastro visible para nadie.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.integrations.registry import get_channel
from app.services.contact_service import ContactService


class FakeSession:
    def __init__(self, conversation=None):
        self.conversation = conversation

    async def scalar(self, _stmt):
        return self.conversation


class FakeConversation:
    def __init__(self, channel: str):
        self.channel = channel


# ── El canal se deriva, no se fija ──────────────────────────────────

async def test_contesta_por_donde_entro_la_persona():
    """Entró por Evolution (el QR), sale por Evolution. El follow-up fijaba
    "whatsapp" —la API oficial de Meta— y sin sus credenciales el mensaje se
    descartaba en silencio."""
    svc = ContactService(FakeSession(FakeConversation("evolution")), uuid4())
    assert await svc.outbound_channel(uuid4()) == "evolution"


async def test_respeta_otros_canales():
    """Hardcodear "evolution" reproduciría el mismo error al revés el día que
    alguien conecte la API oficial."""
    svc = ContactService(FakeSession(FakeConversation("whatsapp")), uuid4())
    assert await svc.outbound_channel(uuid4()) == "whatsapp"


async def test_sin_conversacion_no_inventa_canal():
    """None es la respuesta honesta: quien llama decide qué hacer. Devolver un
    canal por defecto mandaría el mensaje a un lugar que nadie eligió."""
    svc = ContactService(FakeSession(None), uuid4())
    assert await svc.outbound_channel(uuid4()) is None


# ── Los canales avisan cuando no pueden enviar ──────────────────────

@pytest.mark.parametrize("name", ["whatsapp", "evolution", "email"])
async def test_sin_credenciales_el_canal_devuelve_skipped(name, monkeypatch, make_settings):
    """El contrato del que depende la escalación del runner: sin credenciales el
    canal NO lanza, devuelve `skipped`. Si algún canal empezara a lanzar, la
    cadena se cortaría antes de avisar."""
    import app.integrations.email as email_mod
    import app.integrations.evolution as evo_mod
    import app.integrations.whatsapp as wa_mod

    vacio = make_settings(
        whatsapp_access_token="", evolution_api_url="", resend_api_key=""
    )
    for mod in (email_mod, evo_mod, wa_mod):
        monkeypatch.setattr(mod, "settings", vacio)

    result = await get_channel(name).send(to="+5491100000000", body="hola")
    assert result.status == "skipped"
    assert result.raw.get("reason") == "no_credentials"


def test_los_tres_canales_estan_registrados():
    """Si un canal desaparece del registro, `get_channel` lanza NotFoundError y
    el agente falla con un error opaco en vez de un aviso accionable."""
    for name in ("whatsapp", "evolution", "email"):
        assert get_channel(name).name in {name, "resend"}
