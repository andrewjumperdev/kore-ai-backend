"""Event subscribers — they wire the §04 agent chain and the §05 escalation
rules. Importing this module registers them on the bus. Each handler runs in a
worker with its own DB session + tenant context bound by the dispatcher; keep
them idempotent.

Chain: lead.created → SDR(intake+temp) → qualification.needed → Qualification
       → lead.qualified → (hot ⇒ Proposal | warm/cold ⇒ Follow-up)
       price signal ⇒ Proposal ; deal.closed ⇒ Onboarding.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.core.database import session_scope
from app.core.enums import EscalationReason, Temperature
from app.core.logging import get_logger
from app.events.bus import subscribe
from app.events.schemas import EventEnvelope
from app.events.types import EventName

log = get_logger("handlers")


def _agent_payload(event: EventEnvelope, **extra) -> dict:
    base = {
        "contact_id": event.payload.get("contact_id"),
        "channel": event.payload.get("channel", "whatsapp"),
        "to": event.payload.get("to"),
    }
    base.update(extra)
    return base


@subscribe(EventName.LEAD_CREATED)
async def on_lead_created(event: EventEnvelope) -> None:
    """New lead → SDR intake (assigns initial temperature, no outbound)."""
    from app.tasks.agent_tasks import run_agent_task

    run_agent_task.send(
        agent="sdr", tenant_id=str(event.tenant_id), payload=_agent_payload(event)
    )


@subscribe(EventName.QUALIFICATION_NEEDED)
async def on_qualification_needed(event: EventEnvelope) -> None:
    """SDR handed off → run Qualification (classify or ask one question)."""
    from app.tasks.agent_tasks import run_agent_task

    run_agent_task.send(
        agent="qualification", tenant_id=str(event.tenant_id), payload=_agent_payload(event)
    )


@subscribe(EventName.LEAD_QUALIFIED)
async def on_lead_qualified(event: EventEnvelope) -> None:
    """Differentiated trigger by temperature (§04-03)."""
    from app.tasks.agent_tasks import run_agent_task
    from app.tasks.followup_tasks import ensure_followup_sequence

    temp = event.payload.get("temperature")
    contact_id = event.payload.get("contact_id")
    if temp == Temperature.HOT:
        # Hot → prepare proposal (which escalates to human close, §05).
        run_agent_task.send(
            agent="proposal", tenant_id=str(event.tenant_id), payload=_agent_payload(event)
        )
    elif contact_id:
        ensure_followup_sequence.send(tenant_id=str(event.tenant_id), contact_id=contact_id)


@subscribe(EventName.MESSAGE_RECEIVED)
async def on_message_received(event: EventEnvelope) -> None:
    """Inbound message → mark activity, then route to the right agent: unclassified
    contacts go to Qualification; classified contacts go to Follow-up (P1)."""
    from app.models.contact import Contact
    from app.tasks.agent_tasks import run_agent_task

    contact_id = event.payload.get("contact_id")
    if not contact_id:
        return

    agent = "qualification"
    async with session_scope() as session:
        contact = await session.get(Contact, UUID(contact_id))
        if contact is not None:
            contact.last_activity_at = datetime.now(timezone.utc)
            if contact.temperature != Temperature.UNSET:
                agent = "followup"

    run_agent_task.send(
        agent=agent,
        tenant_id=str(event.tenant_id),
        payload=_agent_payload(event, message=event.payload.get("message", "")),
    )


@subscribe(EventName.HUMAN_ESCALATION)
async def on_human_escalation(event: EventEnvelope) -> None:
    """Price-signal escalations trigger the Proposal Agent to prepare (§05)."""
    from app.tasks.agent_tasks import run_agent_task

    if event.payload.get("reason") == EscalationReason.PRICE_SIGNAL:
        contact_id = event.payload.get("contact_id")
        if contact_id:
            run_agent_task.send(
                agent="proposal",
                tenant_id=str(event.tenant_id),
                payload={"contact_id": contact_id},
            )


@subscribe(EventName.DEAL_CLOSED)
async def on_deal_closed(event: EventEnvelope) -> None:
    """Setup paid → activate the client via the Onboarding Agent (§05)."""
    from app.tasks.agent_tasks import run_agent_task

    run_agent_task.send(
        agent="onboarding", tenant_id=str(event.tenant_id), payload={"trigger": "deal.closed"}
    )


@subscribe(EventName.PLAUD_EXPORTED)
async def on_plaud_exported(event: EventEnvelope) -> None:
    """Capa 01: a Plaud conversation landed → detect pending follow-ups."""
    from app.tasks.followup_tasks import ensure_followup_sequence

    contact_id = event.payload.get("contact_id")
    if contact_id:
        ensure_followup_sequence.send(tenant_id=str(event.tenant_id), contact_id=contact_id)
