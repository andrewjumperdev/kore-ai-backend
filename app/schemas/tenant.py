from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9-]+$")
    # P2: a client must belong to a niche (the replicable model).
    niche_slug: str = Field(description="slug of an existing niche")


class TenantOut(BaseModel):
    id: UUID
    name: str
    slug: str
    niche_id: UUID | None
    is_active: bool
    enabled_modules: list
    diagnosis_completed_at: datetime | None
    activated_at: datetime | None
    business_profile: dict
    model_config = {"from_attributes": True}


class TenantCreated(TenantOut):
    # The raw API key is returned exactly once, at creation.
    api_key: str
