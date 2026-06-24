"""Canonical event names. Use the constants — never string literals — so the
set of events stays greppable and typo-proof. Names mirror the §04 chain and
the §05 escalation rules."""
from __future__ import annotations

from enum import StrEnum


class EventName(StrEnum):
    # Capa 01 — captura
    LEAD_CREATED = "lead.created"
    PLAUD_EXPORTED = "plaud.exported"
    MESSAGE_RECEIVED = "message.received"
    MESSAGE_SENT = "message.sent"

    # Cadena de agentes (§04)
    AGENT_RESPONDED = "agent.responded"
    LEAD_QUALIFIED = "lead.qualified"
    TEMPERATURE_CHANGED = "contact.temperature_changed"
    QUALIFICATION_NEEDED = "qualification.needed"
    FOLLOWUP_SCHEDULED = "followup.scheduled"
    PROPOSAL_PREPARED = "proposal.prepared"
    CONTENT_GENERATED = "content.generated"
    ONBOARDING_STARTED = "onboarding.started"

    # Hitos de negocio
    CONTACT_CREATED = "contact.created"
    DIAGNOSIS_COMPLETED = "diagnosis.completed"
    DEAL_CLOSED = "deal.closed"
    TENANT_ACTIVATED = "tenant.activated"

    # Human-in-the-loop (P3) y orquestador (§05)
    HUMAN_ESCALATION = "human.escalation_requested"
    PIPELINE_STALE = "orchestrator.pipeline_stale"
    LEAD_OVERCONTACTED = "orchestrator.lead_overcontacted"

    # Billing (§08)
    SUBSCRIPTION_UPDATED = "billing.subscription_updated"
    SETUP_PAID = "billing.setup_paid"
    SUBSCRIPTION_CANCELED = "billing.subscription_canceled"
