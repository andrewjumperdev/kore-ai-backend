from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.crm import DEAL_STAGES


class CompanyOut(BaseModel):
    id: UUID
    name: str
    domain: str | None = None
    industry: str | None = None
    size: str | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    domain: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=120)
    size: str | None = Field(default=None, max_length=32)


class DealOut(BaseModel):
    id: UUID
    title: str
    stage: str
    amount_cents: int | None = None
    currency: str = "USD"
    expected_close_date: date | None = None
    closed_at: datetime | None = None
    lost_reason: str | None = None
    owner: str | None = None
    contact_id: UUID | None = None
    company_id: UUID | None = None
    created_at: datetime
    # Se completan al listar, para que la tabla no tenga que resolver cada
    # nombre por separado.
    contact_name: str | None = None
    company_name: str | None = None
    model_config = {"from_attributes": True}


class DealCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    contact_id: UUID | None = None
    company_id: UUID | None = None
    # En centavos. El cliente piensa en pesos o dólares enteros; la conversión
    # la hace el frontend, acá entra el entero para no arrastrar floats.
    amount_cents: int | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    stage: str = "new"
    expected_close_date: date | None = None
    owner: str | None = Field(default=None, max_length=120)


class DealUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    stage: str | None = None
    amount_cents: int | None = Field(default=None, ge=0)
    expected_close_date: date | None = None
    lost_reason: str | None = None
    owner: str | None = Field(default=None, max_length=120)
    company_id: UUID | None = None


class StageSummary(BaseModel):
    stage: str
    count: int
    # Suma de los montos conocidos. `count` puede ser mayor que la cantidad de
    # oportunidades que aportan al total: las que todavía no tienen monto se
    # cuentan pero no suman, y mentir un 0 ahí desfiguraría el pipeline.
    amount_cents: int
    with_amount: int


class PipelineOut(BaseModel):
    stages: list[StageSummary]
    open_amount_cents: int
    won_amount_cents: int
    currency: str = "USD"
    # Días promedio entre la creación y el cierre de las ganadas. None cuando
    # todavía no se ganó ninguna: un "0 días" sería una mentira optimista.
    avg_days_to_close: float | None = None


STAGES = DEAL_STAGES
