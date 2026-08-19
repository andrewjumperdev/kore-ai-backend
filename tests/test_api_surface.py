"""Tests de la superficie HTTP real: que las rutas caras estén efectivamente
cerradas. Los tests unitarios verifican las funciones de auth; estos verifican
que están *cableadas* en las rutas, que es donde se cometen los descuidos.

No tocan Postgres: todos los casos deben cortar en la capa de auth, antes de la
primera query. Que eso siga siendo cierto es parte de lo que se afirma acá.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings

TENANT = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"


class StubRedis:
    """Evita que el lifespan espere el timeout de un Redis que no existe."""

    async def ping(self):
        return True

    async def aclose(self):
        return None


class StubSession:
    """Sesión que no consulta nada: las rutas bajo prueba cortan antes de la
    primera query, y si alguna dejara de hacerlo el test lo delata acá."""

    async def scalar(self, _stmt):
        return None

    def add(self, _obj):
        pass

    async def flush(self):
        pass


@contextmanager
def build_client(**overrides):
    """App aislada con settings inyectados en los módulos que los leen.

    Los handlers leen ``settings`` de su módulo en cada llamada, así que la
    inyección se revierte al salir: sin eso, un test que construye una app de
    desarrollo dejaría a los siguientes evaluando reglas de dev contra una app
    de producción, y el fallo aparecería en otro archivo.
    """
    import app.api.deps as deps
    import app.api.v1.webhooks as webhooks
    import app.core.ratelimit as ratelimit
    import app.core.webhook_auth as webhook_auth
    import app.main as main

    settings = Settings(_env_file=None, **overrides)  # type: ignore[call-arg]
    with pytest.MonkeyPatch.context() as mp:
        for module in (main, deps, webhooks, webhook_auth, ratelimit):
            mp.setattr(module, "settings", settings)
        mp.setattr(main, "redis_client", StubRedis())

        app = main.create_app()
        app.dependency_overrides[deps.get_db] = lambda: StubSession()
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client


@pytest.fixture(scope="module")
def prod_client():
    with build_client(
        env="production",
        secret_key="a" * 64,
        provisioning_secret="prov-secret",
        admin_api_key="admin-secret",
        webhook_token="hook-secret",
        rate_limit_enabled=False,
    ) as client:
        yield client


# ── Alta de tenants ─────────────────────────────────────────────────

def test_crear_tenant_sin_secreto_es_401(prod_client):
    """Abierto, este endpoint emite una API key válida a cualquiera."""
    resp = prod_client.post(
        "/api/v1/tenants",
        json={"name": "Intruso", "slug": "intruso", "niche_slug": "real-estate"},
    )
    assert resp.status_code == 401


def test_crear_tenant_con_secreto_incorrecto_es_401(prod_client):
    resp = prod_client.post(
        "/api/v1/tenants",
        json={"name": "Intruso", "slug": "intruso", "niche_slug": "real-estate"},
        headers={"x-provisioning-secret": "adivinado"},
    )
    assert resp.status_code == 401


# ── Webhooks ────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", ["evolution", "plaud", "whatsapp"])
def test_webhook_sin_token_es_401(prod_client, path):
    resp = prod_client.post(f"/api/v1/webhooks/{path}/{TENANT}", json={"data": {}})
    assert resp.status_code == 401


def test_webhook_con_token_incorrecto_es_401(prod_client):
    resp = prod_client.post(
        f"/api/v1/webhooks/evolution/{TENANT}?token=adivinado", json={"data": {}}
    )
    assert resp.status_code == 401


def test_webhook_con_token_correcto_pasa_la_auth(prod_client):
    """Control del control: confirma que los 401 de arriba vienen de la
    verificación del token y no de un 404 de ruteo disfrazado."""
    resp = prod_client.post(
        f"/api/v1/webhooks/evolution/{TENANT}?token=hook-secret", json={"data": {}}
    )
    assert resp.status_code != 401


def test_webhook_acepta_el_token_por_header(prod_client):
    resp = prod_client.post(
        f"/api/v1/webhooks/evolution/{TENANT}",
        json={"data": {}},
        headers={"x-webhook-token": "hook-secret"},
    )
    assert resp.status_code != 401


# ── Endpoints de tenant ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "path",
    ["/api/v1/contacts", "/api/v1/metrics", "/api/v1/escalations", "/api/v1/billing/summary"],
)
def test_endpoints_de_tenant_exigen_api_key(prod_client, path):
    assert prod_client.get(path).status_code == 401


@pytest.mark.parametrize("accion", ["pause", "resume"])
def test_el_freno_de_conversacion_exige_api_key(prod_client, accion):
    """El kill switch es una operación privilegiada como cualquier otra: nadie
    debe poder silenciar (ni reactivar) al agente de otro sin credencial."""
    resp = prod_client.post(f"/api/v1/contacts/{TENANT}/{accion}")
    assert resp.status_code == 401


def test_apagar_una_cuenta_no_acepta_api_key_de_tenant(prod_client):
    """Un cliente no puede reactivarse solo tras un apagado del operador."""
    resp = prod_client.post(
        "/api/v1/tenants/admin/active",
        json={"tenant_id": TENANT, "is_active": True},
        headers={"Authorization": "Bearer kore_la_key_del_cliente"},
    )
    assert resp.status_code == 401


def test_apagar_una_cuenta_acepta_la_llave_de_operador(prod_client):
    resp = prod_client.post(
        "/api/v1/tenants/admin/active",
        json={"tenant_id": TENANT, "is_active": False},
        headers={"x-admin-key": "admin-secret"},
    )
    assert resp.status_code != 401


@pytest.mark.parametrize("ruta", ["/api/v1/onboarding/reset", "/api/v1/onboarding/diagnose"])
def test_el_onboarding_exige_api_key(prod_client, ruta):
    """`reset` borra el diagnóstico y apaga los módulos: abierto, sería un
    apagador de cuentas ajenas."""
    assert prod_client.post(ruta, json={}).status_code == 401


def test_el_asistente_exige_api_key(prod_client):
    """ARIA consume LLM en cada turno: abierta sería una pasarela gratuita."""
    resp = prod_client.post("/api/v1/assistant/chat", json={"message": "hola"})
    assert resp.status_code == 401


def test_el_asistente_esta_montado(prod_client):
    """Control de que la ruta existe: un 404 acá significaría que el router no
    quedó incluido y el 401 de arriba estaría pasando por el motivo equivocado."""
    resp = prod_client.post(
        "/api/v1/assistant/chat",
        json={"message": "hola"},
        headers={"Authorization": "Bearer kore_key_invalida"},
    )
    assert resp.status_code != 404


@pytest.mark.parametrize("metodo,ruta", [("GET", "/api/v1/content"), ("POST", "/api/v1/content")])
def test_el_banco_de_contenido_exige_api_key(prod_client, metodo, ruta):
    """El banco es contenido del negocio de un cliente: no puede leerse ni
    escribirse sin su credencial."""
    resp = prod_client.request(metodo, ruta, json={})
    assert resp.status_code == 401


def test_billing_admin_no_acepta_api_key_de_tenant(prod_client):
    """Un cliente no debe poder declararse pagado con su propia credencial."""
    resp = prod_client.post(
        "/api/v1/billing/admin/setup/paid",
        json={"tenant_id": TENANT},
        headers={"Authorization": "Bearer kore_la_key_del_cliente"},
    )
    assert resp.status_code == 401


def test_billing_admin_acepta_la_llave_de_operador(prod_client):
    """Con la llave correcta pasa la auth y sigue hasta la base (que no existe
    en el test): lo que importa es que NO corte en 401."""
    resp = prod_client.post(
        "/api/v1/billing/admin/setup/paid",
        json={"tenant_id": TENANT},
        headers={"x-admin-key": "admin-secret"},
    )
    assert resp.status_code != 401


def test_stripe_webhook_sin_firma_es_401(prod_client):
    resp = prod_client.post("/api/v1/billing/webhooks/stripe", json={"type": "invoice.paid"})
    assert resp.status_code in (401, 503)  # 503 si no hay secreto configurado


# ── Meta ────────────────────────────────────────────────────────────

def test_health_no_requiere_auth(prod_client):
    resp = prod_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_docs_apagadas_en_produccion(prod_client):
    assert prod_client.get("/docs").status_code == 404
    assert prod_client.get("/openapi.json").status_code == 404


def test_docs_encendidas_en_desarrollo():
    with build_client(env="development", rate_limit_enabled=False) as client:
        assert client.get("/docs").status_code == 200


def test_correlacion_de_request_id(prod_client):
    resp = prod_client.get("/health", headers={"x-request-id": "abc-123"})
    assert resp.headers["x-request-id"] == "abc-123"
