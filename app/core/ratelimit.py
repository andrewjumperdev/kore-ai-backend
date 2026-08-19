"""Rate limiting con Redis — ventana fija, contadores atómicos (INCR + EXPIRE).

Por qué propio y no slowapi: ya tenemos un pool async de Redis y el limitador
que necesitamos son ~30 líneas. Evitamos una dependencia más en el camino
crítico de cada request.

**Fail-open a propósito**: si Redis no responde, se deja pasar la request y se
loguea. Un incidente de Redis no debe convertirse en una caída total de la API;
el rate limit protege de abuso, no es un control de integridad.
"""
from __future__ import annotations

import time

from fastapi import Request

from app.core.config import settings
from app.core.exceptions import RateLimitExceeded
from app.core.logging import get_logger
from app.core.redis import redis_client

log = get_logger("ratelimit")


def client_ip(request: Request) -> str:
    """IP del cliente detrás del reverse proxy.

    Caddy *appendea* su peer real a X-Forwarded-For, así que la entrada de más a
    la derecha es la única que el cliente no puede falsificar. Tomar la primera
    (lo habitual) permitiría evadir el límite mandando un XFF inventado.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


async def hit(bucket: str, *, limit: int, window: int = 60) -> None:
    """Cuenta un evento en ``bucket``. Lanza RateLimitExceeded si se pasó."""
    if not settings.rate_limit_enabled or limit <= 0:
        return

    now = int(time.time())
    key = f"rl:{bucket}:{now // window}"
    try:
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window)
        count, _ = await pipe.execute()
    except Exception as exc:  # Redis caído → no bloquear tráfico legítimo
        log.warning("ratelimit.unavailable", error=str(exc))
        return

    if int(count) > limit:
        retry_after = window - (now % window)
        log.warning("ratelimit.exceeded", bucket=bucket, limit=limit)
        raise RateLimitExceeded(
            f"Límite de {limit} peticiones por {window}s alcanzado",
            retry_after=retry_after,
        )


class RateLimit:
    """Dependencia FastAPI que limita por IP.

        @router.post("", dependencies=[Depends(RateLimit("tenants:create", 20, 3600))])
    """

    def __init__(self, name: str, limit: int, window: int = 60):
        self.name = name
        self.limit = limit
        self.window = window

    async def __call__(self, request: Request) -> None:
        await hit(f"{self.name}:{client_ip(request)}", limit=self.limit, window=self.window)
