from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SubscriptionCreate(BaseModel):
    plan: str = Field(description="e.g. constructoras-growth")
    setup_fee_cents: int = Field(ge=0, default=0)
    mrr_cents: int = Field(ge=0, default=0)


class BillingSummaryOut(BaseModel):
    plan: str | None
    status: str
    mrr_cents: int
    setup_fee_cents: int
    setup_paid: bool = False
    current_period_end: datetime | None = None
