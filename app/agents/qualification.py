"""Qualification Agent (§04-03) — clasificación.

Classifies the lead's temperature (🔴 cold / 🟡 warm / 🟢 hot) using the niche's
explicit signals. If there isn't enough data to classify, it asks ONE active
clarifying question to the lead before classifying (this is the only outbound
communication allowed pre-temperature). If it still cannot classify, it escalates
to the Orchestrator.
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


class QualificationAgent(BaseAgent):
    name = "qualification"

    def role_instructions(self, ctx: AgentContext) -> str:
        signals = ctx.niche_config.get("qualification_signals", {})
        return (
            "You classify a lead's temperature from EXPLICIT signals using the "
            f"niche signal map: {signals}. If the available data is insufficient, "
            "ask exactly ONE concise clarifying question instead of guessing. Only "
            "classify when you have a real signal."
        )

    def output_contract(self) -> str:
        return (
            "Return JSON: {can_classify: boolean, "
            "temperature: 'cold'|'warm'|'hot'|'unknown', "
            "clarifying_question: string|null, rationale: string}."
        )

    def shape_result(self, ctx: AgentContext, data: dict) -> AgentResult:
        can = bool(data.get("can_classify", False))
        temp = data.get("temperature", "unknown")

        if can and temp in ("cold", "warm", "hot"):
            return AgentResult(agent=self.name, output=data, temperature=temp)

        # Not classifiable yet → ask one question (allowed for qualification),
        # OR escalate to the orchestrator if we have no question to ask.
        question = data.get("clarifying_question")
        if question:
            return AgentResult(
                agent=self.name,
                output=data,
                needs_qualification=True,
                messages=[
                    OutboundMessage(
                        channel=ctx.input.get("channel", "whatsapp"),
                        body=question,
                        to=ctx.input.get("to"),
                    )
                ],
            )
        return AgentResult(
            agent=self.name,
            output=data,
            needs_qualification=True,
            escalations=[
                EscalationIntent(
                    reason=EscalationReason.CANNOT_CLASSIFY,
                    title="Lead no clasificable automáticamente",
                    executive_summary=data.get("rationale", ""),
                    payload={"contact_id": str(ctx.contact_id) if ctx.contact_id else None},
                )
            ],
        )


register_agent(QualificationAgent())
