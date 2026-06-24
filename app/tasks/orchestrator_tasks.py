"""Orchestrator sweep (§05/§08). Runs the deterministic rules (stale pipeline,
overcontacted leads) and produces the supervisor report per tenant. Scheduled
daily by the scheduler process."""
from __future__ import annotations

from uuid import UUID

import dramatiq
from sqlalchemy import select

from app.core.context import tenant_context
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.tenant import Tenant
from app.orchestrator.metrics import MetricsService
from app.orchestrator.rules import OrchestratorRules
from app.tasks.broker import run_async

log = get_logger("orchestrator_tasks")


@dramatiq.actor(queue_name="orchestrator")
def run_orchestrator_sweep(tenant_id: str) -> None:
    async def _run() -> None:
        tid = UUID(tenant_id)
        with tenant_context(tid):
            async with session_scope() as session:
                rules_result = await OrchestratorRules(session, tid).sweep()
                snapshot = await MetricsService(session, tid).snapshot()
                log.info("orchestrator.sweep", tenant_id=tenant_id,
                         alerts=len(snapshot.get("alerts", [])), **rules_result)

    run_async(_run())


@dramatiq.actor(queue_name="orchestrator")
def run_all_orchestrator_sweeps() -> None:
    async def _run() -> list[str]:
        async with session_scope() as session:
            ids = (
                await session.scalars(select(Tenant.id).where(Tenant.is_active.is_(True)))
            ).all()
        return [str(i) for i in ids]

    for tid in run_async(_run()):
        run_orchestrator_sweep.send(tid)
    log.info("orchestrator.sweep_dispatched")
