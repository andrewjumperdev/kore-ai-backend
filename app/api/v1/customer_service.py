"""Endpoint del agente de atención al cliente para el canal web (dashboard).

El front (BFF) pega acá; el flujo es el mismo que el de WhatsApp pero sin buffer:
corre el agente sobre el mensaje, ejecuta la reserva si corresponde y devuelve la
respuesta. Auth por API key de tenant (igual que /agents/run)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import DbSession, TenantId
from app.services.contact_service import ContactService
from app.services.customer_service_service import CustomerServiceService

router = APIRouter()


class CSMessageIn(BaseModel):
    message: str = Field(min_length=1)
    name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None


class CSMessageOut(BaseModel):
    reply: str
    intent: str | None = None
    booking: dict = Field(default_factory=dict)
    booking_result: dict | None = None
    run_id: str


@router.post("/message", response_model=CSMessageOut)
async def cs_message(body: CSMessageIn, tenant_id: TenantId, session: DbSession) -> CSMessageOut:
    contact_id = None
    if body.contact_phone or body.contact_email:
        contact, _ = await ContactService(session, tenant_id).get_or_create(
            email=body.contact_email, phone=body.contact_phone, full_name=body.name
        )
        contact_id = contact.id

    result = await CustomerServiceService(session, tenant_id).respond(
        text=body.message,
        contact_id=contact_id,
        push_name=body.name,
        channel="web",
    )
    return CSMessageOut(**result)
