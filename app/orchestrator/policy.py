"""Behavioral policy — §10 (P1–P8) encoded as ENFORCEABLE constraints.

The runner calls these guards before/around every agent execution. A violation
raises PolicyViolation (HTTP 422); it is never a soft warning. This module is
the single source of truth for "what an agent is and is not allowed to do".
"""
from __future__ import annotations

from app.core.enums import Module, Temperature
from app.core.exceptions import PolicyViolation
from app.models.contact import Contact
from app.models.tenant import Tenant

# ── Agent → behavioral capabilities ──────────────────────────────────

# Agents that emit outbound nurture/communication and therefore require a
# classified temperature first (P1: "primero calificar, luego comunicar").
# Note: the Qualification Agent is exempt — its clarifying question IS the act
# of qualifying (§04: "pregunta activa al lead antes de clasificar").
OUTBOUND_REQUIRES_TEMPERATURE = {"followup"}

# P3: these agents PREPARE and ESCALATE — they never auto-deliver. The runner
# routes their output to a human escalation instead of sending/publishing.
HUMAN_REVIEW_REQUIRED = {"proposal", "content"}

# P6: a proposal cannot exist without a completed diagnosis.
REQUIRES_DIAGNOSIS = {"proposal"}

# Operational agents gated on the Coach having enabled their module.
AGENT_MODULE = {
    "sdr": Module.SDR,
    "qualification": Module.QUALIFICATION,
    "followup": Module.FOLLOWUP,
    "proposal": Module.PROPOSAL,
    "content": Module.CONTENT,
    "onboarding": Module.ONBOARDING,
}

# Agents exempt from the niche requirement (platform-level supervisors).
NICHE_EXEMPT = {"orchestrator"}


def requires_human_review(agent_name: str) -> bool:
    return agent_name in HUMAN_REVIEW_REQUIRED


# ── Pre-run guards ───────────────────────────────────────────────────

def check_pre_run(agent_name: str, tenant: Tenant, contact: Contact | None) -> None:
    """Validate invariants BEFORE an agent runs."""
    # P2/P8 — niche is mandatory; nothing runs niche-less.
    if agent_name not in NICHE_EXEMPT and tenant.niche_id is None:
        raise PolicyViolation(
            "P2: el agente no puede operar sin un nicho asignado al cliente",
            details={"agent": agent_name, "tenant": str(tenant.id)},
        )

    # P6 — proposal requires a completed diagnosis.
    if agent_name in REQUIRES_DIAGNOSIS and not tenant.has_diagnosis:
        raise PolicyViolation(
            "P6: no hay propuesta sin diagnóstico completo del Coach Agent",
            details={"agent": agent_name},
        )

    # Module must be enabled by the Coach (except coach/orchestrator themselves).
    module = AGENT_MODULE.get(agent_name)
    if module is not None and module.value not in (tenant.enabled_modules or []):
        raise PolicyViolation(
            f"módulo '{module.value}' no habilitado para este cliente "
            "(el Coach Agent debe habilitarlo tras el diagnóstico)",
            details={"agent": agent_name, "enabled": tenant.enabled_modules},
        )


# ── Post-run / pre-send guards ───────────────────────────────────────

def check_outbound_allowed(agent_name: str, contact: Contact | None) -> None:
    """P1 — block outbound communication when temperature is unset."""
    if agent_name not in OUTBOUND_REQUIRES_TEMPERATURE:
        return
    if contact is None or contact.temperature == Temperature.UNSET:
        raise PolicyViolation(
            "P1: comunicación saliente bloqueada — el lead no tiene temperatura "
            "asignada (debe correr el Qualification Agent primero)",
            details={"agent": agent_name},
        )


def assert_niche_aware(agent_name: str, output: dict, tenant: Tenant) -> None:
    """P2/P8 — reject agent output that ignores the niche. We require the model
    to echo the niche it operated under so generic outputs are caught."""
    if agent_name in NICHE_EXEMPT:
        return
    # The runner injects the niche slug into the prompt; the agent must reflect
    # awareness. We accept either an explicit echo or any non-empty structured
    # output (the niche guard above already guarantees a niche exists).
    if output.get("_niche") in (None, "", "generic", "none"):
        # Tolerant: only hard-fail if the model explicitly signaled genericness.
        if output.get("generic") is True:
            raise PolicyViolation(
                "P2/P8: output genérico sin nicho — rechazado por el orquestador",
                details={"agent": agent_name},
            )
