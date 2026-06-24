from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class EscalationOut(BaseModel):
    id: UUID
    reason: str
    status: str
    source_agent: str | None
    contact_id: UUID | None
    title: str
    executive_summary: str
    payload: dict
    created_at: datetime
    resolved_at: datetime | None
    model_config = {"from_attributes": True}


class EscalationResolve(BaseModel):
    status: str = "resolved"  # resolved | dismissed | acknowledged
    note: str | None = None
