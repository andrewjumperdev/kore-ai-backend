from __future__ import annotations

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
