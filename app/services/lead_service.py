"""Lead intake. Creating a lead emits lead.created, which the SDR agent picks
up asynchronously (see app.events.handlers)."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.bus import event_bus
from app.events.types import EventName
from app.models.lead import Lead
from app.services.contact_service import ContactService


class LeadService:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    async def create_lead(
        self,
        *,
        full_name: str | None,
        email: str | None,
        phone: str | None,
        channel: str = "whatsapp",
        source: str = "api",
        attributes: dict | None = None,
    ) -> Lead:
        lead = Lead(
            tenant_id=self.tenant_id,
            full_name=full_name,
            email=email,
            phone=phone,
            channel=channel,
            source=source,
            attributes=attributes or {},
        )
        self.session.add(lead)
        await self.session.flush()

        # Materialize a Contact immediately so dedup/memory/billing have a home.
        contacts = ContactService(self.session, self.tenant_id)
        contact, _ = await contacts.get_or_create(
            email=email, phone=phone, full_name=full_name, attributes=attributes
        )

        await event_bus.emit(
            self.session,
            EventName.LEAD_CREATED,
            source="lead_service",
            subject_type="lead",
            subject_id=str(lead.id),
            payload={
                "lead_id": str(lead.id),
                "contact_id": str(contact.id),
                "channel": channel,
                "to": phone or email,
            },
        )
        return lead
