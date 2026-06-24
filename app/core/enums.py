"""Shared domain enums. The vocabulary of the spec lives here so it stays
consistent across models, agents, the orchestrator policy, and the API."""
from __future__ import annotations

from enum import StrEnum


class Temperature(StrEnum):
    """Lead temperature per §04. Categorical, never a raw numeric score."""

    COLD = "cold"   # 🔴 frío
    WARM = "warm"   # 🟡 tibio
    HOT = "hot"     # 🟢 caliente
    UNSET = "unset"  # not yet classified — agents may NOT communicate outbound (P1)


class Module(StrEnum):
    """Capabilities the Coach Agent enables for a client after diagnosis."""

    SDR = "sdr"
    QUALIFICATION = "qualification"
    FOLLOWUP = "followup"
    PROPOSAL = "proposal"
    CONTENT = "content"
    ONBOARDING = "onboarding"
    CUSTOMER_SERVICE = "customer_service"  # atención al cliente (FAUSTO): responde + agenda


class NicheStatus(StrEnum):
    ACTIVE = "active"            # caso de uso propio en producción (Plaud Argentina)
    BUILDING = "building"        # en construcción / prioridad
    PLANNED = "planned"          # roadmap (Fase 2)


class EscalationReason(StrEnum):
    PRICE_SIGNAL = "price_signal"            # lead pregunta precio → Proposal
    CLOSE_READY = "close_ready"             # caliente confirmado → cierre humano
    CANNOT_CLASSIFY = "cannot_classify"      # Qualification no pudo clasificar
    PIPELINE_STALE = "pipeline_stale"        # sin movimiento > 7 días
    OVERCONTACTED = "overcontacted"          # mismo lead > 4x sin avance
    CONTENT_REVIEW = "content_review"        # P3 — contenido requiere revisión
    PROPOSAL_REVIEW = "proposal_review"      # P3 — propuesta requiere cierre humano
    TECH_BLOCK = "tech_block"                # Onboarding bloqueado técnicamente
    PAYMENT_CONFIRMATION = "payment_confirmation"  # confirmar pago antes de activar


class EscalationStatus(StrEnum):
    OPEN = "open"
    ACK = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class LifecycleStage(StrEnum):
    LEAD = "lead"
    QUALIFIED = "qualified"
    IN_PROPOSAL = "in_proposal"
    CUSTOMER = "customer"
    LOST = "lost"
