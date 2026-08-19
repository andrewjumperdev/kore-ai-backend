"""Autenticación de webhooks entrantes.

Es la superficie más expuesta del sistema: la URL lleva el tenant_id y el
proveedor la llama sin credenciales de usuario. Si esto se rompe, cualquiera
inyecta mensajes en el CRM de un cliente y nos gasta el presupuesto de LLM.
"""
from __future__ import annotations

import pytest
from starlette.requests import Request

from app.core import webhook_auth
from app.core.exceptions import AuthenticationError, ConfigurationError

SECRET = "s3creto-compartido"


def make_request(query: str = "", headers: dict | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/webhooks/evolution/x",
            "query_string": query.encode(),
            "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
            "client": ("203.0.113.5", 1234),
        }
    )


@pytest.fixture
def prod_settings(monkeypatch, make_settings):
    settings = make_settings(
        env="production",
        secret_key="a" * 64,
        provisioning_secret="prov",
        webhook_token=SECRET,
    )
    monkeypatch.setattr(webhook_auth, "settings", settings)
    return settings


def test_acepta_token_por_query(prod_settings):
    webhook_auth.verify_webhook_token(make_request(query=f"token={SECRET}"), "evolution")


def test_acepta_token_por_header(prod_settings):
    webhook_auth.verify_webhook_token(
        make_request(headers={"x-webhook-token": SECRET}), "evolution"
    )


def test_rechaza_token_incorrecto(prod_settings):
    with pytest.raises(AuthenticationError):
        webhook_auth.verify_webhook_token(make_request(query="token=adivinado"), "evolution")


def test_rechaza_sin_token(prod_settings):
    with pytest.raises(AuthenticationError):
        webhook_auth.verify_webhook_token(make_request(), "evolution")


def test_rechaza_token_vacio(prod_settings):
    with pytest.raises(AuthenticationError):
        webhook_auth.verify_webhook_token(make_request(query="token="), "evolution")


def test_produccion_sin_secreto_configurado_falla_cerrado(monkeypatch, make_settings):
    """Sin secreto NO se procesa el payload: 503, nunca "dejar pasar"."""
    settings = make_settings(
        env="production",
        secret_key="a" * 64,
        provisioning_secret="prov",
        webhook_token="",
        evolution_webhook_token="solo-evolution",
    )
    monkeypatch.setattr(webhook_auth, "settings", settings)
    with pytest.raises(ConfigurationError):
        webhook_auth.verify_webhook_token(make_request(), "plaud")


def test_desarrollo_sin_secreto_deja_pasar(monkeypatch, make_settings):
    """En local con ngrok/Evolution no queremos pelear con secretos."""
    monkeypatch.setattr(webhook_auth, "settings", make_settings(env="development"))
    webhook_auth.verify_webhook_token(make_request(), "evolution")


def test_token_por_proveedor_no_sirve_para_otro(monkeypatch, make_settings):
    settings = make_settings(webhook_token="generico", evolution_webhook_token="propio")
    monkeypatch.setattr(webhook_auth, "settings", settings)
    webhook_auth.verify_webhook_token(make_request(query="token=propio"), "evolution")
    with pytest.raises(AuthenticationError):
        webhook_auth.verify_webhook_token(make_request(query="token=generico"), "evolution")


# ── Firma HMAC (proveedores estilo Meta) ────────────────────────────

def test_firma_hmac_valida():
    import hashlib
    import hmac

    payload = b'{"evento":"x"}'
    firma = hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()
    webhook_auth.verify_hmac_signature(payload, f"sha256={firma}", SECRET)
    webhook_auth.verify_hmac_signature(payload, firma, SECRET)  # sin prefijo


def test_firma_hmac_invalida():
    with pytest.raises(AuthenticationError):
        webhook_auth.verify_hmac_signature(b'{"evento":"x"}', "sha256=" + "0" * 64, SECRET)


def test_firma_hmac_ausente():
    with pytest.raises(AuthenticationError):
        webhook_auth.verify_hmac_signature(b"{}", None, SECRET)


def test_firma_no_valida_si_cambia_el_cuerpo():
    """La firma cubre el cuerpo CRUDO: alterarlo debe invalidarla."""
    import hashlib
    import hmac

    firma = hmac.new(SECRET.encode(), b'{"monto":100}', hashlib.sha256).hexdigest()
    with pytest.raises(AuthenticationError):
        webhook_auth.verify_hmac_signature(b'{"monto":999999}', firma, SECRET)
