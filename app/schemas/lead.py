from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class LeadCreate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    channel: str = "whatsapp"
    source: str = "api"
    attributes: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_contactable(self):
        if not self.email and not self.phone:
            raise ValueError("a lead needs at least an email or a phone")
        return self


class LeadOut(BaseModel):
    id: UUID
    full_name: str | None
    email: str | None
    phone: str | None
    channel: str
    status: str
    temperature: str
    created_at: datetime
    model_config = {"from_attributes": True}
