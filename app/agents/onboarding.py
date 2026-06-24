"""Onboarding Agent (§04-06) — activación post-deal.

Triggered when a deal is closed and setup is paid. Completes the system setup and
guides the client step by step. The client NEVER configures alone. Escalates to
human support only on a technical block.
"""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent, EscalationIntent
from app.agents.registry import register_agent
from app.core.enums import EscalationReason


class OnboardingAgent(BaseAgent):
    name = "onboarding"

    def role_instructions(self, ctx: AgentContext) -> str:
        return (
            "You activate a newly-closed client: confirm the configured system, "
            "produce a clear step-by-step activation guide for the modules enabled "
            "by the Coach, and walk the client through each step. The client never "
            "configures alone. If you hit a technical blocker, escalate to human "
            "support."
        )

    def output_contract(self) -> str:
        return (
            "Return JSON: {steps: {title: string, detail: string, done: boolean}[], "
            "current_step: integer, blocked: boolean, block_reason: string|null, "
            "summary: string}."
        )

    def shape_result(self, ctx: AgentContext, data: dict) -> AgentResult:
        escalations = []
        if data.get("blocked"):
            escalations.append(
                EscalationIntent(
                    reason=EscalationReason.TECH_BLOCK,
                    title="Onboarding bloqueado técnicamente",
                    executive_summary=data.get("block_reason", ""),
                    payload={"step": data.get("current_step")},
                )
            )
        return AgentResult(
            agent=self.name,
            output=data,
            reply=data.get("summary"),
            escalations=escalations,
        )


register_agent(OnboardingAgent())
