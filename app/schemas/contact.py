from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ContactOut(BaseModel):
    id: UUID
    full_name: str | None
    email: str | None
    phone: str | None
    lifecycle_stage: str
    temperature: str
    attributes: dict = {}
    last_activity_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class ContactUpdate(BaseModel):
    lifecycle_stage: str | None = None
    temperature: str | None = None


class MessageOut(BaseModel):
    id: UUID
    direction: str  # inbound | outbound | system
    role: str
    author_agent: str | None
    body: str
    created_at: datetime
    model_config = {"from_attributes": True}
