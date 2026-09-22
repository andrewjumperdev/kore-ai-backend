"""Contactos (el CRM real). Cada persona que el motor trackea — incluidos los que
entran por WhatsApp — vive acá con su temperatura (🔴🟡🟢) y su etapa de ciclo de
vida. Es la fuente de verdad del pipeline del dashboard."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import DbSession, TenantId
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.memory.long_term import LongTermMemoryStore
from app.models.agent_run import AgentRun
from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.schemas.agent import ContactTrail, TrailFact, TrailStep
from app.schemas.contact import ContactOut, ContactUpdate, MessageOut

router = APIRouter()
log = get_logger("contacts")


@router.get("", response_model=list[ContactOut])
async def list_contacts(
    tenant_id: TenantId,
    session: DbSession,
    stage: str | None = Query(default=None),
    limit: int = Query(default=200, le=500),
) -> list[ContactOut]:
    # Último mensaje entrante como subconsulta correlacionada, no como N+1: el
    # dashboard muestra una lista de contactos con su último mensaje, y pedirlo
    # por separado para cada uno serían decenas de requests por carga.
    last_inbound = (
        select(Message.body)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.contact_id == Contact.id,
            Message.direction == "inbound",
        )
        .order_by(Message.created_at.desc())
        .limit(1)
        .correlate(Contact)
        .scalar_subquery()
    )

    stmt = select(Contact, last_inbound.label("last_message")).where(
        Contact.tenant_id == tenant_id
    )
    if stage:
        stmt = stmt.where(Contact.lifecycle_stage == stage)
    stmt = stmt.order_by(Contact.created_at.desc()).limit(limit)

    rows = await session.execute(stmt)
    out: list[ContactOut] = []
    for contact, last_message in rows.all():
        item = ContactOut.model_validate(contact)
        item.last_message = last_message
        out.append(item)
    return out


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


@router.get("/{contact_id}/trail", response_model=ContactTrail)
async def contact_trail(
    contact_id: UUID,
    tenant_id: TenantId,
    session: DbSession,
    limit: int = Query(default=50, le=200),
) -> ContactTrail:
    """Qué hizo el sistema con esta persona, y en qué se basa lo que cree.

    Dos cosas distintas y las dos necesarias: las corridas dicen qué pasó y
    cuándo; los hechos dicen qué quedó registrado y sobre qué evidencia. Un
    agente que actúa sin dejar nada legible obliga a confiar a ciegas, y
    cuando se equivoca no hay por dónde empezar a mirar.
    """
    contact = await session.get(Contact, contact_id)
    if contact is None or contact.tenant_id != tenant_id:
        raise NotFoundError("Contact not found")

    runs = await session.scalars(
        select(AgentRun)
        .where(AgentRun.tenant_id == tenant_id, AgentRun.contact_id == contact_id)
        .order_by(AgentRun.created_at.desc())
        .limit(limit)
    )
    steps: list[TrailStep] = []
    for run in runs:
        step = TrailStep.model_validate(run)
        # El `reply` sale del output y va recortado: el JSON completo puede ser
        # grande y la línea de tiempo solo necesita de qué se trató.
        reply = (run.output or {}).get("reply")
        step.reply = reply[:280] if isinstance(reply, str) else None
        steps.append(step)

    store = LongTermMemoryStore(session, tenant_id)
    rows = await store.recall_with_provenance("contact", str(contact_id))
    return ContactTrail(
        steps=steps, facts=[TrailFact.model_validate(r) for r in rows]
    )


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


@router.post("/{contact_id}/pause", response_model=ContactOut)
async def pause_contact(
    contact_id: UUID,
    tenant_id: TenantId,
    session: DbSession,
    hours: Annotated[int, Query(ge=1, le=8760)] = 24,
) -> ContactOut:
    """Freno de emergencia por conversación: una persona toma el control.

    A partir de acá el agente deja de responderle a este contacto — el guard
    está en app.orchestrator.policy, así que aplica a TODOS los caminos (la
    respuesta de WhatsApp, las cadenas por evento y el disparo manual desde la
    API), no solo al que se nos ocurra tapar acá.

    Es una pausa con vencimiento, no un apagado permanente: lo más común es
    "dejame atender yo esta charla", y una pausa que hay que acordarse de
    levantar termina siendo un contacto abandonado en silencio.
    """
    contact = await session.get(Contact, contact_id)
    if contact is None or contact.tenant_id != tenant_id:
        raise NotFoundError("Contact not found")
    contact.paused_until = datetime.now(timezone.utc) + timedelta(hours=hours)
    await session.flush()
    log.info("contact.paused", contact_id=str(contact_id), hours=hours)
    return ContactOut.model_validate(contact)


@router.post("/{contact_id}/resume", response_model=ContactOut)
async def resume_contact(
    contact_id: UUID, tenant_id: TenantId, session: DbSession
) -> ContactOut:
    """Devuelve la conversación al agente."""
    contact = await session.get(Contact, contact_id)
    if contact is None or contact.tenant_id != tenant_id:
        raise NotFoundError("Contact not found")
    contact.paused_until = None
    await session.flush()
    log.info("contact.resumed", contact_id=str(contact_id))
    return ContactOut.model_validate(contact)
