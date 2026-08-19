from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DbSession, TenantId
from app.core.config import settings
from app.core.enums import Temperature
from app.core.webhook_auth import tenant_capture_token
from app.models.lead import Lead
from app.schemas.lead import LeadCreate, LeadOut
from app.services.lead_service import LeadService

router = APIRouter()


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
async def create_lead(body: LeadCreate, tenant_id: TenantId, session: DbSession) -> LeadOut:
    """Ingest a lead. Emits lead.created → SDR agent makes first contact async."""
    lead = await LeadService(session, tenant_id).create_lead(
        full_name=body.full_name,
        email=body.email,
        phone=body.phone,
        channel=body.channel,
        source=body.source,
        attributes=body.attributes,
    )
    return LeadOut.model_validate(lead)


class SourceStat(BaseModel):
    source: str
    total: int
    last_at: datetime | None
    unqualified: int


@router.get("/sources", response_model=list[SourceStat])
async def lead_sources(tenant_id: TenantId, session: DbSession) -> list[SourceStat]:
    """De dónde vienen los leads, con datos reales.

    Es una agregación sobre `leads.source` — el valor que trae cada captura. No
    hay atribución de campaña ni de anuncio: eso requeriría integrarse con cada
    plataforma. Lo que sí se puede afirmar es por qué puerta entró cada lead, y
    cuántos de esos siguen sin calificar, que es la señal de si esa fuente trae
    volumen o trae ruido.
    """
    rows = await session.execute(
        select(
            Lead.source,
            func.count(Lead.id),
            func.max(Lead.created_at),
            func.count(Lead.id).filter(Lead.temperature == Temperature.UNSET),
        )
        .where(Lead.tenant_id == tenant_id)
        .group_by(Lead.source)
        .order_by(func.count(Lead.id).desc())
    )
    return [
        SourceStat(source=source, total=total, last_at=last_at, unqualified=unqualified)
        for source, total, last_at, unqualified in rows.all()
    ]


class CaptureUrlOut(BaseModel):
    """La URL que el cliente pega en su formulario, su Zap o su CRM viejo."""

    url: str
    example_payload: dict


@router.get("/capture-url", response_model=CaptureUrlOut)
async def capture_url(tenant_id: TenantId) -> CaptureUrlOut:
    """URL de captura de este cliente, con su token propio.

    `source` viaja en la query para que el cliente sepa de dónde vino cada lead:
    una URL por origen (formulario, Instagram, referidos) y el dashboard después
    puede decir cuál trae volumen y cuál trae ruido.
    """
    base = settings.public_base_url.rstrip("/")
    token = tenant_capture_token(str(tenant_id))
    return CaptureUrlOut(
        url=f"{base}/api/v1/webhooks/lead/{tenant_id}?source=web&token={token}",
        # Los nombres de campo son flexibles (ver _ALIAS en webhooks.py); este
        # ejemplo muestra la forma mínima, no un contrato rígido.
        example_payload={
            "nombre": "Sofía Ramírez",
            "email": "sofia@ejemplo.com",
            "telefono": "+5491133334444",
            "zona": "Palermo",
        },
    )
