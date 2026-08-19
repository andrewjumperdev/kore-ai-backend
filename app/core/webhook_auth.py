"""Autenticación de webhooks entrantes.

Todo webhook de KORE es un endpoint público (el proveedor debe alcanzarlo), así
que el único control posible es un secreto compartido o una firma. Reglas:

* Se acepta el secreto por ``?token=`` o por el header ``x-webhook-token``.
* La comparación es en tiempo constante (evita distinguir secretos por timing).
* Sin secreto configurado: en producción el endpoint responde 503 — **fail
  closed**, nunca procesa un payload no autenticado. En desarrollo deja pasar y
  loguea un warning, para no romper el flujo local con Evolution/ngrok.

Proveedores que firman el payload (Stripe) no usan esto: verifican la firma
criptográfica contra el cuerpo crudo, que es más fuerte.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import Request

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConfigurationError
from app.core.logging import get_logger

log = get_logger("webhook_auth")


def verify_webhook_token(request: Request, provider: str) -> None:
    """Valida el secreto compartido del webhook. Lanza si no es válido."""
    expected = settings.webhook_token_for(provider)

    if not expected:
        if settings.is_production:
            log.error("webhook.no_token_configured", provider=provider)
            raise ConfigurationError(
                f"El webhook de '{provider}' no tiene secreto configurado. "
                "Seteá WEBHOOK_TOKEN (o el token específico del proveedor)."
            )
        log.warning("webhook.unauthenticated_dev", provider=provider)
        return

    provided = request.query_params.get("token") or request.headers.get("x-webhook-token")
    if not provided or not secrets.compare_digest(provided, expected):
        log.warning("webhook.unauthorized", provider=provider)
        raise AuthenticationError("Invalid webhook token")


def verify_hmac_signature(
    payload: bytes, signature: str | None, secret: str, *, algo: str = "sha256"
) -> None:
    """Verifica una firma HMAC hex del cuerpo crudo (patrón Meta/WhatsApp).

    ``signature`` puede venir con prefijo (``sha256=…``), se normaliza.
    """
    if not secret:
        if settings.is_production:
            raise ConfigurationError("Falta el secreto para verificar la firma del webhook")
        return
    if not signature:
        raise AuthenticationError("Missing webhook signature")
    provided = signature.split("=", 1)[-1].strip()
    expected = hmac.new(secret.encode(), payload, getattr(hashlib, algo)).hexdigest()
    if not hmac.compare_digest(provided, expected):
        raise AuthenticationError("Invalid webhook signature")
