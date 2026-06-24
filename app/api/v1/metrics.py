from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbSession, TenantId
from app.orchestrator.metrics import MetricsService

router = APIRouter()


@router.get("")
async def get_metrics(tenant_id: TenantId, session: DbSession) -> dict:
    """The orchestrator's tenant metrics snapshot (§08) with threshold alerts."""
    return await MetricsService(session, tenant_id).snapshot()
