from __future__ import annotations

from fastapi import APIRouter

from app.agents.runner import AgentRunner
from app.api.deps import DbSession, TenantId
from app.core.config import settings
from app.core.ratelimit import hit
from app.schemas.agent import AgentEnqueued, AgentRunOut, AgentRunRequest

router = APIRouter()


@router.post("/run", response_model=AgentRunOut | AgentEnqueued)
async def run_agent(body: AgentRunRequest, tenant_id: TenantId, session: DbSession):
    """Run any agent in the chain. ``mode=sync`` executes inline and returns the
    structured output; ``mode=async`` enqueues it on the worker.

    All policy (P1–P8), temperature changes, module enabling (Coach), and human
    escalations (P3) are handled inside the runner — never in the endpoint.

    Limitado por tasa **por tenant**: cada corrida cuesta una llamada al LLM, así
    que es el endpoint más caro de la API. El techo mensual de tokens lo aplica
    el runner (app.billing.quota), que cubre también el camino asíncrono."""
    await hit(f"agents:run:{tenant_id}", limit=settings.rate_limit_agent_per_minute)

    if body.mode == "async":
        from app.tasks.agent_tasks import run_agent_task

        run_agent_task.send(agent=body.agent, tenant_id=str(tenant_id), payload=body.payload)
        return AgentEnqueued(agent=body.agent)

    run = await AgentRunner(session, tenant_id).run(body.agent, body.payload)
    return AgentRunOut.model_validate(run)
