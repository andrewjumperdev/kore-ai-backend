"""Buffer anti-mensajes-múltiples del agente de atención al cliente — Fase 2 y 4
de FAUSTO, con Redis en vez de MongoDB y endurecido para producción.

Diseño (equivale a STOP / WAIT / PROCESS del flujo, pero apto para concurrencia):
  • Cada inbound: dedup por message_id (webhooks se reintentan) → push a la lista
    del chat → set "último message_id" → programa una task con delay = 8s.
  • Al dispararse la task: CLAIM atómico (Lua). Si seguís siendo el último mensaje,
    renombra la lista a una clave de claim (drena atómicamente) y borra el "último";
    si llegó uno más nuevo, STOP (su task se encarga). El claim hace el proceso
    idempotente: si el agente/envío falla, el retry de Dramatiq reusa el mismo claim
    en vez de perder o duplicar mensajes.
  • Tras responder OK: borra el claim (Fase 4 — limpieza).
"""
from __future__ import annotations

import json
from uuid import UUID

import dramatiq

from app.core.config import settings
from app.core.context import tenant_context
from app.core.database import session_scope
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.tasks.broker import run_async

log = get_logger("cs_tasks")

_TTL = 600  # 10 min, igual que el TTL de FAUSTO

# CLAIM atómico: si last_key == message_id, renombra buf→claim (si existe) y borra
# last. Devuelve 1 si lo reclamó este intento, 0 si ya no es el último.
_CLAIM_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  if redis.call('EXISTS', KEYS[2]) == 1 then
    redis.call('RENAME', KEYS[2], KEYS[3])
    redis.call('EXPIRE', KEYS[3], ARGV[2])
  end
  redis.call('DEL', KEYS[1])
  return 1
end
return 0
"""


def _buf_key(t: str, c: str) -> str:
    return f"cs:buf:{t}:{c}"


def _last_key(t: str, c: str) -> str:
    return f"cs:last:{t}:{c}"


def _seen_key(t: str, c: str, m: str) -> str:
    return f"cs:seen:{t}:{c}:{m}"


def _claim_key(t: str, c: str, m: str) -> str:
    return f"cs:claim:{t}:{c}:{m}"


async def buffer_and_schedule(
    *,
    tenant_id: str,
    chat_id: str,
    content: str,
    message_id: str,
    is_audio: bool = False,
    push_name: str | None = None,
) -> bool:
    """Guarda el mensaje en el buffer y programa el procesamiento (Fase 2).
    Devuelve False si era un webhook duplicado (mismo message_id)."""
    r = get_redis()
    # Anti-duplicados: el primer SET NX gana; reintentos del webhook no re-insertan.
    if message_id:
        fresh = await r.set(_seen_key(tenant_id, chat_id, message_id), "1", nx=True, ex=_TTL)
        if not fresh:
            log.info("cs.duplicate_skipped", chat_id=chat_id, message_id=message_id)
            return False

    doc = json.dumps(
        {"content": content, "is_audio": is_audio, "push_name": push_name, "message_id": message_id}
    )
    await r.rpush(_buf_key(tenant_id, chat_id), doc)
    await r.expire(_buf_key(tenant_id, chat_id), _TTL)
    await r.set(_last_key(tenant_id, chat_id), message_id, ex=_TTL)
    process_buffer_task.send_with_options(
        args=(tenant_id, chat_id, message_id),
        delay=settings.cs_buffer_seconds * 1000,
    )
    log.info("cs.buffered", chat_id=chat_id, message_id=message_id)
    return True


@dramatiq.actor(max_retries=3, min_backoff=2_000, queue_name="customer_service", time_limit=120_000)
def process_buffer_task(tenant_id: str, chat_id: str, message_id: str) -> None:
    async def _run() -> None:
        import redis.asyncio as aioredis

        from app.integrations.evolution import evolution_channel
        from app.services.contact_service import ContactService
        from app.services.customer_service_service import CustomerServiceService

        # Cliente Redis FRESCO atado al loop de esta task (el worker corre un loop
        # nuevo por invocación; el pool global tiene locks atados a otro loop).
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            claim_key = _claim_key(tenant_id, chat_id, message_id)

            # Claim atómico. Idempotente ante retries: si ya hay un claim de un
            # intento previo (que falló después de drenar), lo retomamos.
            claimed = await r.eval(
                _CLAIM_LUA, 3,
                _last_key(tenant_id, chat_id), _buf_key(tenant_id, chat_id), claim_key,
                message_id, str(_TTL),
            )
            if not claimed and not await r.exists(claim_key):
                log.info("cs.stop_newer_message", chat_id=chat_id, message_id=message_id)
                return

            raw = await r.lrange(claim_key, 0, -1)
            msgs = [json.loads(x) for x in raw]
            if not msgs:
                await r.delete(claim_key)
                return

            combined = "\n".join(
                (("🎤 [audio]: " if m.get("is_audio") else "") + (m.get("content") or "")) for m in msgs
            ).strip()
            push_name = msgs[-1].get("push_name")

            tid = UUID(tenant_id)
            with tenant_context(tid):
                async with session_scope() as session:
                    contacts = ContactService(session, tid)
                    contact, _ = await contacts.get_or_create(phone=chat_id, full_name=push_name)
                    result = await CustomerServiceService(session, tid).respond(
                        text=combined, contact_id=contact.id, push_name=push_name, channel="evolution",
                    )
                    reply = result.get("reply") or ""
                    if reply:
                        await evolution_channel.send(to=chat_id, body=reply)

            # Limpiamos el claim sólo tras responder OK (Fase 4). Si algo falla
            # antes, el claim queda y el retry de Dramatiq lo reprocesa.
            await r.delete(claim_key)
            log.info("cs.processed", chat_id=chat_id, messages=len(msgs), intent=result.get("intent"))
        finally:
            await r.aclose()

    run_async(_run())
