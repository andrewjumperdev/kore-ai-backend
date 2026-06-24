"""Inbound webhooks (Capa 01 — captura). Channel webhooks turn provider payloads
into normalized inbound messages → record + emit message.received → the chain
routes the reply. Plaud exports are ingested into the CRM as structured data.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request

from app.api.deps import DbSession
from app.core.context import set_current_tenant
from app.core.exceptions import AuthenticationError
from app.core.logging import get_logger
from app.events.bus import event_bus
from app.events.types import EventName
from app.integrations.evolution import evolution_channel
from app.integrations.plaud import PlaudConnector, PlaudExport
from app.integrations.registry import get_channel
from app.integrations.transcription import transcription
from app.services.contact_service import ContactService
from app.tasks.customer_service_tasks import buffer_and_schedule

router = APIRouter()
log = get_logger("webhooks")


@router.post("/plaud/{tenant_id}")
async def plaud_export(tenant_id: UUID, request: Request, session: DbSession):
    """Capa 01: ingest a Plaud recording (transcript + summary + action items)."""
    set_current_tenant(tenant_id)
    payload = await request.json()
    export = PlaudExport.from_payload(payload)
    contact_id = await PlaudConnector(session, tenant_id).ingest(export)
    return {"ingested": True, "contact_id": str(contact_id)}


@router.post("/evolution/{tenant_id}")
async def evolution_inbound(tenant_id: UUID, request: Request):
    """Atención al cliente (FAUSTO): recibe WhatsApp vía Evolution, transcribe el
    audio si hace falta y lo manda al buffer de 8s (Fase 1+2). El agente responde
    desde la task del buffer."""
    from app.core.config import settings

    # Verificación opcional del webhook (producción): ?token= o header x-webhook-token.
    expected = settings.evolution_webhook_token
    if expected:
        provided = request.query_params.get("token") or request.headers.get("x-webhook-token")
        if provided != expected:
            log.warning("webhook.evolution_unauthorized", tenant=str(tenant_id))
            raise AuthenticationError("Invalid webhook token")

    set_current_tenant(tenant_id)
    payload = await request.json()
    messages = evolution_channel.parse_webhook(payload)

    scheduled = 0
    for msg in messages:
        is_audio = bool(msg.raw.get("is_audio"))
        content = msg.text
        if is_audio and msg.provider_message_id:
            audio = await evolution_channel.get_media_base64(msg.provider_message_id)
            if audio:
                content = await transcription.transcribe(audio)
        if not content:
            continue
        if await buffer_and_schedule(
            tenant_id=str(tenant_id),
            chat_id=msg.from_identity,
            content=content,
            message_id=msg.provider_message_id or "",
            is_audio=is_audio,
            push_name=msg.raw.get("push_name"),
        ):
            scheduled += 1

    return {"buffered": scheduled}


@router.post("/{channel}/{tenant_id}")
async def inbound_message(channel: str, tenant_id: UUID, request: Request, session: DbSession):
    """Receive an inbound message from a channel provider.

    NOTE: verify the provider signature before trusting the payload (omitted for
    brevity — wire it into get_channel(...).verify())."""
    set_current_tenant(tenant_id)
    payload = await request.json()
    messages = get_channel(channel).parse_webhook(payload)
    contacts = ContactService(session, tenant_id)

    for msg in messages:
        identity = msg.from_identity
        is_email = "@" in identity
        contact, _ = await contacts.get_or_create(
            email=identity if is_email else None,
            phone=None if is_email else identity,
        )
        conversation = await contacts.get_or_create_conversation(contact.id, channel)
        await contacts.record_message(
            conversation_id=conversation.id,
            direction="inbound",
            body=msg.text,
            role="user",
            meta={"provider_message_id": msg.provider_message_id},
        )
        await event_bus.emit(
            session,
            EventName.MESSAGE_RECEIVED,
            source=channel,
            subject_type="contact",
            subject_id=str(contact.id),
            payload={
                "contact_id": str(contact.id),
                "conversation_id": str(conversation.id),
                "channel": channel,
                "message": msg.text,
                "to": identity,
            },
        )

    return {"received": len(messages)}
