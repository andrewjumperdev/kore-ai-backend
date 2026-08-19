"""Reporte de errores a Sentry — opcional y sin dependencia dura.

Sin ``SENTRY_DSN`` no hace nada, y si el paquete no está instalado tampoco
rompe: la observabilidad no debe ser un motivo para que la app no arranque.

Lo importante en producción es que un 500 en un webhook o una cadena de agentes
deje rastro en algún lado que no sea `docker logs`, que rota y se pierde.
"""
from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("observability")

# Campos que nunca deben salir del proceso, aunque Sentry los capture del scope
# local de un frame (los agentes manipulan credenciales de tenants).
_SCRUB_KEYS = (
    "api_key", "apikey", "password", "token", "secret",
    "authorization", "hashed_key", "dsn",
)


def _scrub(event: dict, _hint: dict) -> dict:
    """before_send: enmascara valores sensibles en request headers y extras."""
    request = event.get("request") or {}
    headers = request.get("headers") or {}
    for key in list(headers):
        if any(s in key.lower() for s in _SCRUB_KEYS):
            headers[key] = "[filtered]"
    extra = event.get("extra") or {}
    for key in list(extra):
        if any(s in key.lower() for s in _SCRUB_KEYS):
            extra[key] = "[filtered]"
    return event


def init_sentry() -> None:
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        log.warning("sentry.sdk_missing", hint="pip install sentry-sdk")
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        # PII fuera: los payloads llevan conversaciones de clientes finales.
        send_default_pii=False,
        before_send=_scrub,
    )
    log.info("sentry.enabled", environment=settings.env)
