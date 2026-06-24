"""Contact + conversation resolution and identity normalization.

The ``identity_key`` is what makes billing dedup and memory work: a single
normalized handle per person per tenant. Phones are reduced to digits; emails
are lowercased. Everything else routes through here so the rule lives in one
place.
"""
from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.bus import event_bus
from app.events.types import EventName
from app.models.contact import Contact
from app.models.conversation import Conversation, Message


def normalize_identity(*, email: str | None = None, phone: str | None = None) -> str:
    if email:
        return email.strip().lower()
    if phone:
        digits = re.sub(r"\D", "", phone)
        return f"+{digits}" if digits else phone.strip()
    raise ValueError("contact requires an email or phone to build identity_key")


class ContactService:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    async def get_or_create(
        self,
        *,
        email: str | None = None,
        phone: str | None = None,
        full_name: str | None = None,
        attributes: dict | None = None,
    ) -> tuple[Contact, bool]:
        identity = normalize_identity(email=email, phone=phone)
        existing = await self.session.scalar(
            select(Contact).where(
                Contact.tenant_id == self.tenant_id,
                Contact.identity_key == identity,
            )
        )
        if existing:
            return existing, False

        contact = Contact(
            tenant_id=self.tenant_id,
            identity_key=identity,
            email=email,
            phone=phone,
            full_name=full_name,
            attributes=attributes or {},
        )
        self.session.add(contact)
        await self.session.flush()
        await event_bus.emit(
            self.session,
            EventName.CONTACT_CREATED,
            source="contact_service",
            subject_type="contact",
            subject_id=str(contact.id),
            payload={"contact_id": str(contact.id), "identity": identity},
        )
        return contact, True

    async def get_or_create_conversation(
        self, contact_id: UUID, channel: str
    ) -> Conversation:
        conv = await self.session.scalar(
            select(Conversation).where(
                Conversation.tenant_id == self.tenant_id,
                Conversation.contact_id == contact_id,
                Conversation.channel == channel,
                Conversation.status == "open",
            )
        )
        if conv:
            return conv
        conv = Conversation(
            tenant_id=self.tenant_id, contact_id=contact_id, channel=channel
        )
        self.session.add(conv)
        await self.session.flush()
        return conv

    async def record_message(
        self,
        *,
        conversation_id: UUID,
        direction: str,
        body: str,
        role: str = "user",
        author_agent: str | None = None,
        meta: dict | None = None,
    ) -> Message:
        msg = Message(
            tenant_id=self.tenant_id,
            conversation_id=conversation_id,
            direction=direction,
            role=role,
            author_agent=author_agent,
            body=body,
            meta=meta or {},
        )
        self.session.add(msg)
        await self.session.flush()
        return msg
