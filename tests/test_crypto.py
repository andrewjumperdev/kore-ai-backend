"""Cifrado de credenciales de integraciones en reposo."""
from __future__ import annotations

from app.core import crypto


def test_roundtrip():
    assert crypto.decrypt(crypto.encrypt("hunter2")) == "hunter2"


def test_el_cifrado_no_deja_el_valor_a_la_vista():
    encrypted = crypto.encrypt("smtp-password-real")
    assert "smtp-password-real" not in encrypted
    assert encrypted.startswith(crypto.PREFIX)


def test_encrypt_es_idempotente():
    """Un `set` parcial re-guarda valores ya cifrados; no deben cifrarse dos veces."""
    once = crypto.encrypt("secreto")
    assert crypto.encrypt(once) == once
    assert crypto.decrypt(once) == "secreto"


def test_valor_en_claro_pasa_derecho():
    """Compatibilidad con lo guardado antes de este cambio."""
    assert crypto.decrypt("legacy-en-claro") == "legacy-en-claro"


def test_vacio_no_se_cifra():
    assert crypto.encrypt("") == ""
    assert crypto.decrypt("") == ""


def test_dato_corrupto_devuelve_vacio_en_vez_de_explotar():
    """Ante clave rotada, la integración debe verse "no configurada", no romper."""
    assert crypto.decrypt(crypto.PREFIX + "basura-que-no-es-fernet") == ""


def test_identifica_claves_sensibles():
    assert crypto.is_secret_key("password")
    assert crypto.is_secret_key("api_key")
    assert crypto.is_secret_key("smtp_password")   # por sufijo
    assert crypto.is_secret_key("refresh_token")
    assert crypto.is_secret_key("CLIENT_SECRET")   # case-insensitive
    assert not crypto.is_secret_key("host")
    assert not crypto.is_secret_key("from_email")


def test_encrypt_config_solo_toca_lo_sensible():
    config = {"host": "smtp.gmail.com", "port": 587, "password": "p4ss", "user": "yo@x.com"}
    encrypted = crypto.encrypt_config(config)

    assert encrypted["host"] == "smtp.gmail.com"   # legible: no es secreto
    assert encrypted["port"] == 587                # los no-str quedan intactos
    assert encrypted["password"].startswith(crypto.PREFIX)
    assert crypto.decrypt_config(encrypted) == config
