"""Contactos (el CRM real). Cada persona que el motor trackea — incluidos los que
entran por WhatsApp — vive acá con su temperatura (🔴🟡🟢) y su etapa de ciclo de
vida. Es la fuente de verdad del pipeline del dashboard."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import DbSession, TenantId
from app.core.exceptions import NotFoundError
from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.schemas.contact import ContactOut, ContactUpdate, MessageOut

router = APIRouter()


@router.get("", response_model=list[ContactOut])
async def list_contacts(
    tenant_id: TenantId,
    session: DbSession,
    stage: str | None = Query(default=None),
    limit: int = Query(default=200, le=500),
) -> list[ContactOut]:
    stmt = select(Contact).where(Contact.tenant_id == tenant_id)
    if stage:
        stmt = stmt.where(Contact.lifecycle_stage == stage)
    stmt = stmt.order_by(Contact.created_at.desc()).limit(limit)
    rows = await session.scalars(stmt)
    return [ContactOut.model_validate(c) for c in rows]


@router.get("/{contact_id}/messages", response_model=list[MessageOut])
async def contact_messages(contact_id: UUID, tenant_id: TenantId, session: DbSession) -> list[MessageOut]:
    """Historial de la conversación del contacto (para el panel de detalle)."""
    contact = await session.get(Contact, contact_id)
    if contact is None or contact.tenant_id != tenant_id:
        raise NotFoundError("Contact not found")
    rows = await session.scalars(
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.contact_id == contact_id, Message.tenant_id == tenant_id)
        .order_by(Message.created_at)
    )
    return [MessageOut.model_validate(m) for m in rows]


@router.patch("/{contact_id}", response_model=ContactOut)
async def update_contact(
    contact_id: UUID, body: ContactUpdate, tenant_id: TenantId, session: DbSession
) -> ContactOut:
    """Actualiza la etapa (drag del kanban) o la temperatura de un contacto."""
    contact = await session.get(Contact, contact_id)
    if contact is None or contact.tenant_id != tenant_id:
        raise NotFoundError("Contact not found")
    if body.lifecycle_stage is not None:
        contact.lifecycle_stage = body.lifecycle_stage
    if body.temperature is not None:
        contact.temperature = body.temperature
    await session.flush()
    return ContactOut.model_validate(contact)
