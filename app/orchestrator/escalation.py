"""Human-in-the-loop service (P3). Creates an escalation with an executive
summary for Silvana/Andrew and emits the corresponding event."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EscalationReason
from app.core.logging import get_logger
from app.events.bus import event_bus
from app.events.types import EventName
from app.models.escalation import Escalation

log = get_logger("escalation")


class EscalationService:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    async def raise_escalation(
        self,
        *,
        reason: EscalationReason,
        title: str,
        executive_summary: str = "",
        source_agent: str | None = None,
        contact_id: UUID | None = None,
        payload: dict | None = None,
    ) -> Escalation:
        esc = Escalation(
            tenant_id=self.tenant_id,
            reason=reason,
            title=title,
            executive_summary=executive_summary,
            source_agent=source_agent,
            contact_id=contact_id,
            payload=payload or {},
        )
        self.session.add(esc)
        await self.session.flush()
        await event_bus.emit(
            self.session,
            EventName.HUMAN_ESCALATION,
            source=source_agent or "orchestrator",
            subject_type="escalation",
            subject_id=str(esc.id),
            payload={
                "escalation_id": str(esc.id),
                "reason": str(reason),
                "contact_id": str(contact_id) if contact_id else None,
            },
        )
        log.info("escalation.raised", reason=str(reason), title=title)
        return esc
