"""Deterministic orchestrator rules (§05). These run on a periodic sweep over the
pipeline and raise escalations / pause contacts. They are the hard-coded safety
net; the Orchestrator Agent adds human-readable synthesis on top.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EscalationReason, LifecycleStage
from app.core.logging import get_logger
from app.models.contact import Contact
from app.orchestrator.escalation import EscalationService

log = get_logger("orchestrator.rules")

STALE_DAYS = 7          # §05: pipeline sin movimiento > 7 días → alerta
OVERCONTACT_LIMIT = 4   # §05: mismo lead > 4x sin avance → pausa + flag
PAUSE_DAYS = 30         # §05: follow-up — pausa 30 días


class OrchestratorRules:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.escalations = EscalationService(session, tenant_id)

    async def sweep(self, at: datetime | None = None) -> dict:
        at = at or datetime.now(timezone.utc)
        stale = await self._flag_stale_pipeline(at)
        over = await self._pause_overcontacted(at)
        return {"stale_flagged": stale, "overcontacted_paused": over}

    async def _flag_stale_pipeline(self, at: datetime) -> int:
        cutoff = at - timedelta(days=STALE_DAYS)
        contacts = (
            await self.session.scalars(
                select(Contact).where(
                    Contact.tenant_id == self.tenant_id,
                    Contact.lifecycle_stage.notin_(
                        [LifecycleStage.CUSTOMER, LifecycleStage.LOST]
                    ),
                    Contact.last_activity_at.is_not(None),
                    Contact.last_activity_at < cutoff,
                )
            )
        ).all()
        for c in contacts:
            await self.escalations.raise_escalation(
                reason=EscalationReason.PIPELINE_STALE,
                title="Pipeline sin movimiento > 7 días",
                executive_summary=f"Contacto {c.id} sin actividad desde {c.last_activity_at}.",
                source_agent="orchestrator",
                contact_id=c.id,
                payload={"last_activity_at": str(c.last_activity_at)},
            )
        if contacts:
            log.info("rules.stale_flagged", count=len(contacts))
        return len(contacts)

    async def _pause_overcontacted(self, at: datetime) -> int:
        contacts = (
            await self.session.scalars(
                select(Contact).where(
                    Contact.tenant_id == self.tenant_id,
                    Contact.contact_attempts > OVERCONTACT_LIMIT,
                    Contact.paused_until.is_(None),
                )
            )
        ).all()
        for c in contacts:
            c.paused_until = at + timedelta(days=PAUSE_DAYS)
            await self.escalations.raise_escalation(
                reason=EscalationReason.OVERCONTACTED,
                title="Lead contactado > 4x sin avance",
                executive_summary=f"Contacto {c.id} pausado {PAUSE_DAYS}d. "
                "Revisar si el problema es oferta, timing o lead no calificado.",
                source_agent="orchestrator",
                contact_id=c.id,
                payload={"attempts": c.contact_attempts},
            )
        if contacts:
            log.info("rules.overcontacted_paused", count=len(contacts))
        return len(contacts)
