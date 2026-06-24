"""Event bus — the spine of the platform.

emit() does three things atomically-enough for an at-least-once system:
  1. Persists an Event row (append-only audit / analytics source of truth).
  2. Publishes a lightweight envelope to a per-tenant Redis Stream so external
     consumers / websockets can tail in real time.
  3. Enqueues asynchronous fan-out to registered handlers via the task queue,
     so request latency never depends on side effects (sending WhatsApp,
     scoring, billing, etc.).

Handlers register with @subscribe(EventName.X). They run in a worker, each in
its own DB session and tenant context, and must be idempotent.
"""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_current_tenant
from app.core.logging import get_logger
from app.core.redis import redis_client
from app.events.schemas import EventEnvelope
from app.events.types import EventName
from app.models.event import Event

log = get_logger("events")

Handler = Callable[[EventEnvelope], Awaitable[None]]
_subscribers: dict[str, list[Handler]] = defaultdict(list)


def subscribe(*names: EventName) -> Callable[[Handler], Handler]:
    """Register an async handler for one or more event names."""

    def decorator(fn: Handler) -> Handler:
        for name in names:
            _subscribers[str(name)].append(fn)
        return fn

    return decorator


def handlers_for(name: str) -> list[Handler]:
    return list(_subscribers.get(name, []))


class EventBus:
    async def emit(
        self,
        session: AsyncSession,
        name: EventName,
        *,
        payload: dict | None = None,
        source: str = "system",
        subject_type: str | None = None,
        subject_id: str | None = None,
        tenant_id: UUID | None = None,
    ) -> EventEnvelope:
        tid = tenant_id or get_current_tenant()
        event = Event(
            tenant_id=tid,
            name=str(name),
            source=source,
            payload=payload or {},
            subject_type=subject_type,
            subject_id=subject_id,
        )
        session.add(event)
        # Flush to obtain id/seq/created_at without ending the caller's tx.
        await session.flush()
        envelope = EventEnvelope.model_validate(event)

        # Publish + enqueue after the row is durable. We do it post-flush; the
        # outer unit of work still owns the commit. For exactly-once delivery
        # use a transactional outbox table — wired the same way.
        await self._publish_stream(envelope)
        self._enqueue_fanout(envelope)

        log.info("event.emit", name=envelope.name, subject_id=subject_id)
        return envelope

    async def _publish_stream(self, env: EventEnvelope) -> None:
        try:
            await redis_client.xadd(
                f"events:{env.tenant_id}",
                {"data": env.model_dump_json()},
                maxlen=10_000,
                approximate=True,
            )
        except Exception as exc:  # never let stream issues break the request
            log.warning("event.stream_publish_failed", error=str(exc))

    def _enqueue_fanout(self, env: EventEnvelope) -> None:
        # Imported lazily to avoid a circular import (tasks import the bus).
        from app.tasks.event_tasks import dispatch_event

        if handlers_for(env.name):
            dispatch_event.send(json.loads(env.model_dump_json()))


event_bus = EventBus()
