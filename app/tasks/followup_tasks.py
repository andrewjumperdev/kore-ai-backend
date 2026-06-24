"""Follow-up scheduling per §05. ensure_followup_sequence seeds the cadence from
the niche's temperature-specific sequence; each step runs the Follow-up agent,
counts attempts, and applies the rule: no response in ~48h → 1 retry → after
max 2 attempts without response, pause 30 days."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import dramatiq

from app.core.context import tenant_context
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.contact import Contact
from app.models.tenant import Tenant
from app.tasks.broker import run_async

log = get_logger("followup_tasks")
_DAY_MS = 24 * 60 * 60 * 1000
MAX_ATTEMPTS = 2          # §04 Follow-up: máx. 2 intentos sin respuesta
PAUSE_DAYS = 30


async def _niche_sequence(session, tenant: Tenant, temperature: str) -> list[int]:
    from app.services.niche_service import NicheService

    cfg = {}
    if tenant.niche_id:
        niche = await NicheService(session).get(tenant.niche_id)
        cfg = niche.config if niche else {}
    sequences = cfg.get("followup_sequences", {})
    return sequences.get(temperature, [2, 5])


@dramatiq.actor(queue_name="followup")
def ensure_followup_sequence(tenant_id: str, contact_id: str) -> None:
    async def _run() -> None:
        tid = UUID(tenant_id)
        with tenant_context(tid):
            async with session_scope() as session:
                tenant = await session.get(Tenant, tid)
                contact = await session.get(Contact, UUID(contact_id))
                if tenant is None or contact is None or contact.paused_until is not None:
                    return
                seq = await _niche_sequence(session, tenant, contact.temperature)
        delay = (seq[0] if seq else 2) * _DAY_MS
        run_followup_step.send_with_options(args=(tenant_id, contact_id, 0), delay=delay)
        log.info("followup.seeded", contact_id=contact_id, sequence=seq)

    run_async(_run())


@dramatiq.actor(queue_name="followup")
def run_followup_step(tenant_id: str, contact_id: str, step: int) -> None:
    async def _run() -> None:
        from app.agents.runner import AgentRunner

        tid = UUID(tenant_id)
        with tenant_context(tid):
            async with session_scope() as session:
                contact = await session.get(Contact, UUID(contact_id))
                if contact is None or contact.paused_until is not None:
                    return

                # §05: after MAX_ATTEMPTS without response → pause 30 days.
                if contact.contact_attempts >= MAX_ATTEMPTS:
                    contact.paused_until = datetime.now(timezone.utc) + timedelta(days=PAUSE_DAYS)
                    log.info("followup.paused", contact_id=contact_id)
                    return

                tenant = await session.get(Tenant, tid)
                seq = await _niche_sequence(session, tenant, contact.temperature)

                runner = AgentRunner(session, tid)
                run = await runner.run(
                    "followup",
                    {"contact_id": contact_id, "step": step, "trigger": "followup.step",
                     "channel": "whatsapp"},
                )
                # Count this outbound attempt (reset by an inbound reply handler).
                contact.contact_attempts += 1
                output = run.output.get("output", {})

        if output.get("stop_sequence") or output.get("price_signal"):
            return
        next_step = step + 1
        if next_step < len(seq):
            gap = output.get("next_followup_in_days") or seq[next_step]
            run_followup_step.send_with_options(
                args=(tenant_id, contact_id, next_step), delay=int(gap) * _DAY_MS
            )

    run_async(_run())
