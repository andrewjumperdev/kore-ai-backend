from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class EventOut(BaseModel):
    id: UUID
    seq: int
    name: str
    source: str
    subject_type: str | None
    subject_id: str | None
    payload: dict
    created_at: datetime
    model_config = {"from_attributes": True}


class EventPage(BaseModel):
    items: list[EventOut]
    next_cursor: int | None
