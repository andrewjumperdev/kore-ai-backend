"""Follow-up Agent (§04-04) — seguimiento / nurturing.

Runs the niche's temperature-specific sequence. Never leaves a lead without a
response. If the lead asks about price or conditions, it escalates to the
Proposal Agent. Hard limits (max attempts, 30-day pause) are enforced by the
orchestrator, not here.
"""
from __future__ import annotations

from app.agents.base import (
    AgentContext,
    AgentResult,
    BaseAgent,
    EscalationIntent,
    OutboundMessage,
)
from app.agents.registry import register_agent
from app.core.enums import EscalationReason


class FollowUpAgent(BaseAgent):
    name = "followup"

    def role_instructions(self, ctx: AgentContext) -> str:
        sequences = ctx.niche_config.get("followup_sequences", {})
        return (
            "You nurture a classified lead. Add value every time — never just "
            f"'checking in'. Honor the niche cadence for its temperature: {sequences}. "
            "Never promise anything that is not in the system. If the lead asks "
            "about price or conditions, do NOT quote — flag a price signal so it "
            "escalates to the Proposal Agent."
        )

    def output_contract(self) -> str:
        return (
            "Return JSON: {should_send: boolean, reply: string, "
            "next_followup_in_days: integer|null, stop_sequence: boolean, "
            "price_signal: boolean}."
        )

    def shape_result(self, ctx: AgentContext, data: dict) -> AgentResult:
        escalations = []
        messages = []
        if data.get("price_signal"):
            escalations.append(
                EscalationIntent(
                    reason=EscalationReason.PRICE_SIGNAL,
                    title="Lead pregunta precio → preparar propuesta",
                    executive_summary="El lead mostró señal de precio durante el "
                    "follow-up. Disparar Proposal Agent.",
                    payload={"contact_id": str(ctx.contact_id) if ctx.contact_id else None},
                )
            )
        elif data.get("should_send") and data.get("reply"):
            messages.append(
                OutboundMessage(
                    channel=ctx.input.get("channel", "whatsapp"),
                    body=data["reply"],
                    to=ctx.input.get("to"),
                )
            )
        return AgentResult(
            agent=self.name,
            output=data,
            reply=data.get("reply"),
            messages=messages,
            escalations=escalations,
        )


register_agent(FollowUpAgent())
