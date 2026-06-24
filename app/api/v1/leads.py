from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import DbSession, TenantId
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
