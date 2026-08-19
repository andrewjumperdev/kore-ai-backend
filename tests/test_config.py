"""La config de producción es fail-fast: un deploy inseguro no debe arrancar."""
from __future__ import annotations

import pytest

STRONG_SECRET = "a" * 64


def _prod(make_settings, **overrides):
    base = {
        "env": "production",
        "secret_key": STRONG_SECRET,
        "provisioning_secret": "prov-secret",
        "webhook_token": "hook-secret",
    }
    return make_settings(**{**base, **overrides})


def test_production_ok_con_secretos_fuertes(make_settings):
    settings = _prod(make_settings)
    assert settings.is_production
    assert settings.serve_docs is False  # Swagger apagado por defecto en prod


def test_rechaza_secret_key_default(make_settings):
    with pytest.raises(ValueError, match="KORE_SECRET_KEY"):
        _prod(make_settings, secret_key="dev-secret-change-me")


def test_rechaza_secret_key_corta(make_settings):
    with pytest.raises(ValueError, match="KORE_SECRET_KEY"):
        _prod(make_settings, secret_key="corta")


def test_rechaza_provisioning_secret_vacio(make_settings):
    with pytest.raises(ValueError, match="PROVISIONING_SECRET"):
        _prod(make_settings, provisioning_secret="")


def test_rechaza_webhooks_sin_token(make_settings):
    with pytest.raises(ValueError, match="WEBHOOK_TOKEN"):
        _prod(make_settings, webhook_token="")


def test_rechaza_stripe_sin_webhook_secret(make_settings):
    with pytest.raises(ValueError, match="STRIPE_WEBHOOK_SECRET"):
        _prod(make_settings, stripe_api_key="sk_live_x", stripe_webhook_secret="")


def test_rechaza_debug_en_produccion(make_settings):
    with pytest.raises(ValueError, match="DEBUG"):
        _prod(make_settings, debug=True)


def test_desarrollo_no_exige_nada(make_settings):
    """En dev los defaults inseguros son válidos: si no, no se podría laburar."""
    settings = make_settings(env="development")
    assert settings.secret_key == "dev-secret-change-me"
    assert settings.serve_docs is True


def test_token_de_webhook_especifico_pisa_al_generico(make_settings):
    settings = make_settings(webhook_token="generico", evolution_webhook_token="propio")
    assert settings.webhook_token_for("evolution") == "propio"
    assert settings.webhook_token_for("plaud") == "generico"
    assert settings.webhook_token_for("cualquier-otro") == "generico"


def test_cors_cerrado_en_produccion_por_defecto(make_settings):
    assert _prod(make_settings).cors_allow_origins == []
    assert make_settings(env="development").cors_allow_origins == ["*"]


def test_cors_parsea_lista_separada_por_comas(make_settings):
    settings = _prod(make_settings, cors_origins="https://a.com, https://b.com")
    assert settings.cors_allow_origins == ["https://a.com", "https://b.com"]
