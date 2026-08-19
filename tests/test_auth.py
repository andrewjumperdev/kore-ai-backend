"""Autenticación: API keys de tenant y secretos de servicio."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.api import deps
from app.core.exceptions import AuthenticationError, ConfigurationError
from app.core.security import generate_api_key, hash_api_key
from app.models.tenant import TenantApiKey


class FakeSession:
    def __init__(self, row=None):
        self.row = row

    async def scalar(self, _stmt):
        return self.row


# ── API keys de tenant ──────────────────────────────────────────────

def test_la_key_generada_tiene_prefijo_y_entropia():
    raw, hashed = generate_api_key()
    assert raw.startswith("kore_")
    assert len(raw) > 40
    assert hashed == hash_api_key(raw)


def test_dos_keys_nunca_coinciden():
    assert generate_api_key()[0] != generate_api_key()[0]


def test_el_hash_no_revela_la_key():
    raw, hashed = generate_api_key()
    assert raw not in hashed
    assert len(hashed) == 64  # sha256 hex


async def test_acepta_api_key_valida():
    tenant_id = uuid4()
    raw, hashed = generate_api_key()
    session = FakeSession(TenantApiKey(tenant_id=tenant_id, hashed_key=hashed, prefix=raw[:12]))

    assert await deps.get_tenant_id(session, f"Bearer {raw}") == tenant_id


async def test_rechaza_api_key_desconocida():
    with pytest.raises(AuthenticationError):
        await deps.get_tenant_id(FakeSession(None), "Bearer kore_inventada")


async def test_rechaza_header_ausente():
    with pytest.raises(AuthenticationError, match="Missing bearer token"):
        await deps.get_tenant_id(FakeSession(None), None)


async def test_rechaza_esquema_que_no_es_bearer():
    with pytest.raises(AuthenticationError):
        await deps.get_tenant_id(FakeSession(None), "Basic kore_x")


async def test_rechaza_token_que_no_es_api_key():
    """Ya no aceptamos JWT: hay un solo camino de autenticación de tenant."""
    jwt_ish = "eyJhbGciOiJIUzI1NiJ9.eyJ0aWQiOiJ4In0.firma"
    with pytest.raises(AuthenticationError, match="Invalid token"):
        await deps.get_tenant_id(FakeSession(None), f"Bearer {jwt_ish}")


# ── Secretos de servicio ────────────────────────────────────────────

@pytest.fixture
def prod(monkeypatch, make_settings):
    monkeypatch.setattr(
        deps,
        "settings",
        make_settings(
            env="production",
            secret_key="a" * 64,
            provisioning_secret="prov-secret",
            admin_api_key="admin-secret",
            webhook_token="hook",
        ),
    )


async def test_provisioning_acepta_el_secreto(prod):
    await deps.require_provisioning_secret("prov-secret")


async def test_provisioning_rechaza_secreto_incorrecto(prod):
    with pytest.raises(AuthenticationError):
        await deps.require_provisioning_secret("no-es")


async def test_provisioning_rechaza_sin_secreto(prod):
    with pytest.raises(AuthenticationError):
        await deps.require_provisioning_secret(None)


async def test_admin_acepta_su_llave(prod):
    await deps.require_admin("admin-secret")


async def test_admin_no_acepta_el_secreto_de_provisioning(prod):
    """Los secretos no son intercambiables: distinto poder, distinta llave."""
    with pytest.raises(AuthenticationError):
        await deps.require_admin("prov-secret")


async def test_admin_sin_configurar_en_produccion_falla_cerrado(monkeypatch, make_settings):
    """Sin admin_api_key seteada, la operación se rechaza — nunca se abre."""
    monkeypatch.setattr(
        deps,
        "settings",
        make_settings(
            env="production",
            secret_key="a" * 64,
            provisioning_secret="prov",
            webhook_token="hook",
            admin_api_key="",
        ),
    )
    with pytest.raises(ConfigurationError):
        await deps.require_admin("lo-que-sea")


async def test_en_desarrollo_sin_secreto_deja_pasar(monkeypatch, make_settings):
    monkeypatch.setattr(deps, "settings", make_settings(env="development"))
    await deps.require_provisioning_secret(None)
    await deps.require_admin(None)
