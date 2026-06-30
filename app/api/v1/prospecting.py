"""Prospección cold email desde el dashboard. Importás la lista (web+correo),
disparás el batch (scrape → icebreaker → SMTP) y ves el estado. Auth por tenant."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import DbSession, TenantId
from app.services.prospecting_service import ProspectingService

router = APIRouter()


class ProspectRow(BaseModel):
    email: str
    web: str | None = None
    company_name: str | None = None


class ImportIn(BaseModel):
    prospects: list[ProspectRow] = Field(default_factory=list)


class ProspectOut(BaseModel):
    id: UUID
    email: str
    web: str | None
    company_name: str | None
    status: str
    subject: str | None
    sent_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class StatsOut(BaseModel):
    pending: int
    sent: int
    failed: int
    skipped: int = 0
    total: int
    smtp_configured: bool


@router.post("/import")
async def import_prospects(body: ImportIn, tenant_id: TenantId, session: DbSession) -> dict:
    return await ProspectingService(session, tenant_id).import_prospects(
        [r.model_dump() for r in body.prospects]
    )


@router.get("/stats", response_model=StatsOut)
async def stats(tenant_id: TenantId, session: DbSession) -> StatsOut:
    return StatsOut(**await ProspectingService(session, tenant_id).stats())


@router.get("", response_model=list[ProspectOut])
async def list_prospects(tenant_id: TenantId, session: DbSession) -> list[ProspectOut]:
    rows = await ProspectingService(session, tenant_id).list_prospects()
    return [ProspectOut.model_validate(p) for p in rows]


@router.post("/run")
async def run_now(tenant_id: TenantId, session: DbSession) -> dict:
    """Procesa un batch ahora mismo (manual). La task horaria hace lo mismo sola."""
    return await ProspectingService(session, tenant_id).run_batch()
