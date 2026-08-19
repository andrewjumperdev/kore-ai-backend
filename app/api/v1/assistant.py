"""ARIA — el asistente del panel.

Conversa con el dueño de la cuenta sobre su propio sistema. Es un agente
separado del Coach a propósito: el Coach configura al cliente, este solo
responde (ver app/agents/assistant.py).

El hilo de conversación no vive en el CRM. ``Conversation`` exige un
``contact_id`` porque modela la charla con un LEAD, y el dueño de la cuenta no
es un lead suyo: darle una fila en `contacts` lo contaría en el pipeline y
ensuciaría la distribución de temperatura del dashboard. Se usa en cambio un id
determinístico por tenant sobre la memoria de corto plazo (Redis), que no tiene
esa restricción y ya expira sola a las 24 h.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agents.runner import AgentRunner
from app.api.deps import DbSession, TenantId
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.ratelimit import hit
from app.models.tenant import Tenant

router = APIRouter()

# Namespace fijo para derivar el hilo de ARIA de cada tenant. Determinístico a
# propósito: el mismo tenant recupera siempre su hilo entre requests y entre
# reinicios, sin necesidad de guardar el id en ningún lado.
_ARIA_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def aria_thread_id(tenant_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(_ARIA_NAMESPACE, f"aria:{tenant_id}")


class AssistantIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class AssistantOut(BaseModel):
    reply: str


@router.post("/chat", response_model=AssistantOut)
async def chat(body: AssistantIn, tenant_id: TenantId, session: DbSession) -> AssistantOut:
    """Un turno de conversación con ARIA.

    El historial se arma solo: el runner guarda el turno del usuario y el del
    agente en la memoria de corto plazo del hilo, y ``build_user_prompt`` los
    vuelve a leer en el turno siguiente.
    """
    # Mismo techo que /agents/run: cada turno es una llamada al LLM.
    await hit(f"assistant:{tenant_id}", limit=settings.rate_limit_agent_per_minute)

    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found")

    run = await AgentRunner(session, tenant_id).run(
        "assistant",
        {
            "message": body.message,
            "conversation_id": str(aria_thread_id(tenant_id)),
            # Se le pasan los módulos para que pueda hablar del sistema REAL del
            # cliente y no del catálogo genérico.
            "enabled_modules": tenant.enabled_modules or [],
        },
    )
    out = run.output or {}
    data = out.get("output", {}) if isinstance(out.get("output"), dict) else {}
    return AssistantOut(reply=out.get("reply") or data.get("reply") or "")
