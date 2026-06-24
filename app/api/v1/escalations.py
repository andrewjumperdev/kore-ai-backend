from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import DbSession, TenantId
from app.core.exceptions import NotFoundError
from app.models.escalation import Escalation
from app.schemas.escalation import EscalationOut, EscalationResolve

router = APIRouter()


@router.get("", response_model=list[EscalationOut])
async def list_escalations(
    tenant_id: TenantId,
    session: DbSession,
    status_filter: str | None = Query(default="open", alias="status"),
    limit: int = Query(default=50, le=200),
) -> list[EscalationOut]:
    """The human work queue (P3): proposals to close, content to review, alerts."""
    stmt = select(Escalation).where(Escalation.tenant_id == tenant_id)
    if status_filter:
        stmt = stmt.where(Escalation.status == status_filter)
    stmt = stmt.order_by(Escalation.created_at.desc()).limit(limit)
    rows = await session.scalars(stmt)
    return [EscalationOut.model_validate(e) for e in rows]


@router.post("/{escalation_id}/resolve", response_model=EscalationOut)
async def resolve_escalation(
    escalation_id: UUID, body: EscalationResolve, tenant_id: TenantId, session: DbSession
) -> EscalationOut:
    esc = await session.get(Escalation, escalation_id)
    if esc is None or esc.tenant_id != tenant_id:
        raise NotFoundError("Escalation not found")
    esc.status = body.status
    esc.resolved_at = datetime.now(timezone.utc)
    if body.note:
        esc.payload = {**esc.payload, "resolution_note": body.note}
    await session.flush()
    return EscalationOut.model_validate(esc)
