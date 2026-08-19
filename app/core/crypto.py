"""Cifrado simétrico para credenciales en reposo (Fernet / AES-128-CBC + HMAC).

Las integraciones por tenant guardan secretos de terceros (password SMTP, tokens
de Calendar/ElevenLabs) en un JSONB. En claro, cualquier dump de la base — un
backup filtrado, un `SELECT` desde una consola de soporte — los expone todos.

La clave se deriva por HKDF de ``KORE_CREDENTIALS_SECRET`` (o de ``secret_key``
si no está seteada), así el operador no tiene que manejar un secreto más.
Rotarla vuelve indescifrable lo ya guardado: el cliente tendría que recargar sus
credenciales desde el dashboard.

``decrypt`` acepta texto sin cifrar tal cual: los valores anteriores a este
cambio siguen funcionando y se re-cifran solos la próxima vez que se guardan.
"""
from __future__ import annotations

import base64
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("crypto")

# Marca de versión: distingue un valor cifrado de uno legado en claro y deja
# lugar a rotar de algoritmo sin ambigüedad.
PREFIX = "enc:v1:"

# Claves cuyo valor se cifra al persistir. Se comparan en minúsculas y también
# por sufijo (``smtp_password`` coincide con ``password``).
SECRET_KEYS = frozenset(
    {
        "password",
        "api_key",
        "apikey",
        "token",
        "access_token",
        "refresh_token",
        "client_secret",
        "secret",
        "private_key",
    }
)


@lru_cache
def _fernet() -> Fernet:
    base = (settings.credentials_secret or settings.secret_key).encode()
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"kore-integration-credentials",
    ).derive(base)
    return Fernet(base64.urlsafe_b64encode(key))


def is_secret_key(name: str) -> bool:
    lowered = name.lower()
    return lowered in SECRET_KEYS or any(lowered.endswith(f"_{s}") for s in SECRET_KEYS)


def encrypt(value: str) -> str:
    """Cifra un string. Idempotente: no vuelve a cifrar lo ya cifrado."""
    if not value or value.startswith(PREFIX):
        return value
    return PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """Descifra. Un valor sin prefijo se devuelve tal cual (legado en claro)."""
    if not value or not value.startswith(PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(PREFIX) :].encode()).decode()
    except InvalidToken:
        # Clave rotada o dato corrupto. Devolvemos vacío en vez de propagar: la
        # integración se comporta como "no configurada" y el cliente la recarga.
        log.error("crypto.decrypt_failed")
        return ""


def encrypt_config(config: dict) -> dict:
    """Cifra las claves sensibles de un dict de configuración."""
    return {
        k: encrypt(v) if is_secret_key(k) and isinstance(v, str) else v
        for k, v in config.items()
    }


def decrypt_config(config: dict) -> dict:
    return {
        k: decrypt(v) if is_secret_key(k) and isinstance(v, str) else v
        for k, v in config.items()
    }
