"""Plaud capture connector — Capa 01 (fuente de datos).

Plaud is NOT a messaging channel (we never send through it); it is a capture
source. An exported recording (transcription + summary + action items) is turned
into structured CRM data: the contact is upserted, the transcript is indexed in
semantic memory, action items are stored as long-term facts, and a
``plaud.exported`` event triggers pending follow-ups.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.events.bus import event_bus
from app.events.types import EventName
from app.memory.manager import MemoryManager
from app.services.contact_service import ContactService

log = get_logger("plaud")


@dataclass
class PlaudExport:
    contact_phone: str | None
    contact_email: str | None
    contact_name: str | None
    transcript: str
    summary: str
    action_items: list[str]

    @classmethod
    def from_payload(cls, payload: dict) -> "PlaudExport":
        c = payload.get("contact", {})
        return cls(
            contact_phone=c.get("phone"),
            contact_email=c.get("email"),
            contact_name=c.get("name"),
            transcript=payload.get("transcript", ""),
            summary=payload.get("summary", ""),
            action_items=payload.get("action_items", []),
        )


class PlaudConnector:
    name = "plaud"

    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.contacts = ContactService(session, tenant_id)
        self.memory = MemoryManager(session, tenant_id)

    async def ingest(self, export: PlaudExport) -> UUID:
        contact, _ = await self.contacts.get_or_create(
            email=export.contact_email,
            phone=export.contact_phone,
            full_name=export.contact_name,
            attributes={"source": "plaud"},
        )
        conversation = await self.contacts.get_or_create_conversation(contact.id, "plaud")
        await self.contacts.record_message(
            conversation_id=conversation.id,
            direction="inbound",
            body=export.transcript[:8000],
            role="user",
            meta={"summary": export.summary, "kind": "plaud_transcript"},
        )

        # Summary → semantic memory; action items → long-term facts (P5).
        if export.summary:
            await self.memory.semantic.index(
                "conversation", export.summary, subject_id=str(contact.id),
                meta={"source": "plaud"},
            )
        if export.action_items:
            await self.memory.long.remember(
                "contact", str(contact.id), "plaud_action_items",
                {"items": export.action_items},
            )

        await event_bus.emit(
            self.session,
            EventName.PLAUD_EXPORTED,
            source="plaud",
            subject_type="contact",
            subject_id=str(contact.id),
            payload={
                "contact_id": str(contact.id),
                "action_items": export.action_items,
                "channel": "whatsapp",
            },
        )
        log.info("plaud.ingested", contact_id=str(contact.id), items=len(export.action_items))
        return contact.id
