"""Run an agent off the request path. Triggered by events (lead.created,
contact.scored…) or directly by the /agents/run endpoint for async mode."""
from __future__ import annotations

from uuid import UUID

import dramatiq

from app.core.context import tenant_context
from app.core.database import session_scope
from app.core.logging import get_logger
from app.tasks.broker import run_async

log = get_logger("agent_tasks")


@dramatiq.actor(max_retries=3, queue_name="agents", time_limit=120_000)
def run_agent_task(agent: str, tenant_id: str, payload: dict) -> None:
    async def _run() -> None:
        # Imported here so the worker pulls the whole agent graph lazily.
        from app.agents.runner import AgentRunner

        tid = UUID(tenant_id)
        with tenant_context(tid):
            async with session_scope() as session:
                runner = AgentRunner(session, tid)
                await runner.run(agent, payload)

    log.info("agent_task.start", agent=agent, tenant_id=tenant_id)
    run_async(_run())
