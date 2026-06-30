"""Task horaria de prospección (equivale al Google Sheets Trigger del n8n):
procesa un batch de prospectos pendientes para cada tenant activo."""
from __future__ import annotations

import dramatiq
from sqlalchemy import select

from app.core.context import tenant_context
from app.core.database import session_scope
from app.core.logging import get_logger
from app.tasks.broker import run_async

log = get_logger("prospecting_tasks")


@dramatiq.actor(max_retries=1, queue_name="prospecting", time_limit=300_000)
def run_prospecting_for_tenant(tenant_id: str) -> None:
    async def _run() -> None:
        from uuid import UUID

        from app.services.prospecting_service import ProspectingService

        tid = UUID(tenant_id)
        with tenant_context(tid):
            async with session_scope() as session:
                await ProspectingService(session, tid).run_batch()

    run_async(_run())


@dramatiq.actor(max_retries=1, queue_name="prospecting", time_limit=120_000)
def run_prospecting_all() -> None:
    """Encola un batch por cada tenant activo (lo dispara el scheduler cada hora)."""
    async def _collect() -> list[str]:
        from app.models.tenant import Tenant

        async with session_scope() as session:
            rows = await session.scalars(select(Tenant.id).where(Tenant.is_active.is_(True)))
            return [str(t) for t in rows]

    for tid in run_async(_collect()):
        run_prospecting_for_tenant.send(tid)
    log.info("prospecting.fan_out")
