"""Asynchronous event fan-out. The bus enqueues dispatch_event; this actor runs
every registered handler for the event, each within the event's tenant context.
"""
from __future__ import annotations

import dramatiq

from app.core.context import tenant_context
from app.core.logging import get_logger
from app.events.bus import handlers_for
from app.events.schemas import EventEnvelope
from app.tasks.broker import run_async

# Registering handlers is a side effect of importing this module.
import app.events.handlers  # noqa: F401  (keep last to register subscribers)

log = get_logger("event_tasks")


@dramatiq.actor(max_retries=3, queue_name="events")
def dispatch_event(event: dict) -> None:
    envelope = EventEnvelope.model_validate(event)
    handlers = handlers_for(envelope.name)
    if not handlers:
        return

    async def _run() -> None:
        with tenant_context(envelope.tenant_id):
            for handler in handlers:
                try:
                    await handler(envelope)
                except Exception as exc:  # isolate handler failures
                    log.error(
                        "handler.failed",
                        handler=handler.__name__,
                        event=envelope.name,
                        error=str(exc),
                    )

    run_async(_run())
