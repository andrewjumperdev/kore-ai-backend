"""Captura universal de leads: la URL que el cliente pega en su formulario o Zap.

Cada plataforma nombra los campos a su manera. Si la normalización falla, el
lead se descarta o entra sin teléfono — y el cliente no se entera hasta que
alguien pregunta por qué no llegó nadie.
"""
from __future__ import annotations

import pytest

from app.api.v1.webhooks import _ALIAS, _pick


@pytest.mark.parametrize(
    "payload,esperado",
    [
        ({"email": "a@b.com"}, "a@b.com"),
        ({"correo": "a@b.com"}, "a@b.com"),
        ({"Email": "a@b.com"}, "a@b.com"),          # mayúsculas
        ({"EMAIL_ADDRESS": "a@b.com"}, "a@b.com"),  # estilo Meta / Mailchimp
        ({"e-mail": "a@b.com"}, "a@b.com"),
    ],
)
def test_reconoce_los_alias_de_email(payload, esperado):
    assert _pick(payload, "email") == esperado


@pytest.mark.parametrize(
    "clave", ["phone", "telefono", "teléfono", "celular", "whatsapp", "tel", "phone_number"]
)
def test_reconoce_los_alias_de_telefono(clave):
    assert _pick({clave: "+5491133334444"}, "phone") == "+5491133334444"


def test_ignora_valores_vacios():
    """Un formulario manda todos sus campos, completos o no. Un string vacío no
    es un dato: si contara, el lead entraría sin forma de contacto."""
    assert _pick({"email": "", "correo": "real@x.com"}, "email") == "real@x.com"


def test_recorta_espacios():
    """El copiar y pegar del usuario final trae espacios; sin limpiar, dos leads
    de la misma persona quedan como contactos distintos."""
    assert _pick({"email": "  a@b.com  "}, "email") == "a@b.com"


def test_sin_dato_devuelve_none():
    assert _pick({"otra_cosa": "x"}, "email") is None


def test_respeta_el_orden_de_preferencia():
    """El alias canónico gana sobre los otros: si vienen los dos, `full_name`
    es el que la plataforma llenó a propósito."""
    assert _pick({"name": "Segundo", "full_name": "Primero"}, "full_name") == "Primero"


def test_los_alias_no_se_pisan_entre_campos():
    """"whatsapp" cuenta como teléfono y no como nombre: si un alias sirviera
    para dos campos, el mismo valor terminaría duplicado en ambos."""
    grupos = list(_ALIAS.values())
    for i, grupo in enumerate(grupos):
        for otro in grupos[i + 1 :]:
            assert not (set(grupo) & set(otro))


def test_los_campos_no_reconocidos_no_se_pierden():
    """El contrato de `attributes`: lo que no entendemos se guarda igual. Un
    "zona" o un "presupuesto" del formulario del cliente es justo el contexto
    que el agente necesita para calificar."""
    payload = {"email": "a@b.com", "zona": "Palermo", "presupuesto": "180000"}
    conocidas = {a.lower() for grupo in _ALIAS.values() for a in grupo}
    extras = {k: v for k, v in payload.items() if k.lower() not in conocidas}
    assert extras == {"zona": "Palermo", "presupuesto": "180000"}
