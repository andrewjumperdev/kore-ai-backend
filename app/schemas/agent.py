from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    agent: str = Field(description="coach | sdr | followup | setter | proposal")
    payload: dict = Field(default_factory=dict)
    # sync = run inline and return output; async = enqueue and return run id.
    mode: str = Field(default="sync", pattern="^(sync|async)$")


class AgentRunOut(BaseModel):
    id: UUID
    agent: str
    status: str
    output: dict
    input_tokens: int
    output_tokens: int
    latency_ms: int
    model_config = {"from_attributes": True}


class AgentEnqueued(BaseModel):
    status: str = "enqueued"
    agent: str


# ── El rastro: qué hizo el sistema con este contacto ────────────────
#
# El dato ya existía en `agent_runs` y `long_term_memory`; lo que faltaba era
# poder verlo. Un agente que actúa sin dejar nada legible obliga al cliente a
# confiar a ciegas, y cuando se equivoca no hay por dónde empezar a mirar.


class TrailStep(BaseModel):
    """Una corrida de un agente sobre este contacto."""

    id: UUID
    agent: str
    status: str
    created_at: datetime
    latency_ms: int
    # Lo que el agente respondió, si respondió algo. Se manda recortado: el
    # output completo puede ser un JSON grande y la línea de tiempo solo
    # necesita mostrar de qué se trató.
    reply: str | None = None
    error: str | None = None
    model_config = {"from_attributes": True}


class TrailFact(BaseModel):
    """Un hecho que el sistema cree sobre este contacto, con su respaldo."""

    key: str
    value: dict
    basis: str          # inferred | imported | stated | operator
    source: str
    evidence: str | None = None
    observed_at: datetime | None = None
    model_config = {"from_attributes": True}


class ContactTrail(BaseModel):
    steps: list[TrailStep]
    facts: list[TrailFact]
