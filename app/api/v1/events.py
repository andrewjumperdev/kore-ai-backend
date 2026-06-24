from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import DbSession, TenantId
from app.models.event import Event
from app.schemas.event import EventOut, EventPage

router = APIRouter()


@router.get("", response_model=EventPage)
async def list_events(
    tenant_id: TenantId,
    session: DbSession,
    name: str | None = Query(default=None, description="Filter by event name"),
    after: int | None = Query(default=None, description="Cursor: return seq > after"),
    limit: int = Query(default=50, le=200),
) -> EventPage:
    """Cursor-paginated, tenant-scoped event feed (the audit/analytics stream)."""
    stmt = select(Event).where(Event.tenant_id == tenant_id)
    if name:
        stmt = stmt.where(Event.name == name)
    if after is not None:
        stmt = stmt.where(Event.seq > after)
    stmt = stmt.order_by(Event.seq.asc()).limit(limit)

    rows = list(await session.scalars(stmt))
    next_cursor = rows[-1].seq if len(rows) == limit else None
    return EventPage(
        items=[EventOut.model_validate(r) for r in rows], next_cursor=next_cursor
    )
