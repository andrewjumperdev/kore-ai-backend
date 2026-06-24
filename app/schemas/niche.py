from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class NicheCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9-]+$")
    name: str
    status: str = "building"
    priority: int = 99
    config: dict = Field(default_factory=dict)


class NicheOut(BaseModel):
    id: UUID
    slug: str
    name: str
    status: str
    priority: int
    is_active: bool
    config: dict
    model_config = {"from_attributes": True}
