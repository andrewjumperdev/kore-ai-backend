"""Techo mensual de tokens LLM por tenant.

No es facturación (KORE cobra setup + MRR, ver app.billing.engine): es un
cortafuegos de costos. Un tenant con un loop de mensajes, un webhook abusado o
un bot conversando solo puede quemar cientos de dólares de API en horas. El
contador vive en Redis porque se toca en cada corrida de agente y no necesita
ser transaccional — perder algunas cuentas ante un reinicio es aceptable.

``token_quota_monthly = 0`` (default) desactiva el límite.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.core.config import settings
from app.core.exceptions import QuotaExceeded
from app.core.logging import get_logger
from app.core.redis import redis_client

log = get_logger("quota")

_TTL_SECONDS = 60 * 60 * 24 * 40  # ~40 días: cubre el mes y se limpia solo


def _key(tenant_id: UUID | str, at: datetime | None = None) -> str:
    period = (at or datetime.now(timezone.utc)).strftime("%Y-%m")
    return f"quota:tokens:{tenant_id}:{period}"


async def current_usage(tenant_id: UUID | str) -> int:
    try:
        raw = await redis_client.get(_key(tenant_id))
    except Exception as exc:
        log.warning("quota.unavailable", error=str(exc))
        return 0
    return int(raw or 0)


async def check(tenant_id: UUID | str) -> None:
    """Lanza QuotaExceeded (402) si el tenant ya superó su techo mensual."""
    limit = settings.token_quota_monthly
    if limit <= 0:
        return
    used = await current_usage(tenant_id)
    if used >= limit:
        log.warning("quota.exceeded", tenant_id=str(tenant_id), used=used, limit=limit)
        raise QuotaExceeded(
            "Alcanzaste el límite mensual de tokens del plan. "
            "Escribinos para ampliarlo.",
            details={"used": used, "limit": limit},
        )


async def record(tenant_id: UUID | str, tokens: int) -> None:
    """Suma tokens consumidos. Nunca interrumpe el flujo si Redis falla."""
    if settings.token_quota_monthly <= 0 or tokens <= 0:
        return
    try:
        key = _key(tenant_id)
        pipe = redis_client.pipeline()
        pipe.incrby(key, tokens)
        pipe.expire(key, _TTL_SECONDS)
        await pipe.execute()
    except Exception as exc:
        log.warning("quota.record_failed", error=str(exc))
