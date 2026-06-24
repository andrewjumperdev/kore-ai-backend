from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    """The shape published to Redis and persisted to the events table."""

    id: UUID
    tenant_id: UUID
    name: str
    source: str = "system"
    subject_type: str | None = None
    subject_id: str | None = None
    payload: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}
