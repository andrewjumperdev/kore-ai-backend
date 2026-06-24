"""SDR Agent (§04-02) — captación / intake.

Registers a new lead from any channel, assigns an INITIAL temperature from the
available signals, and hands off to the Qualification Agent. It does NOT send
outbound messages — "primero calificar, luego comunicar" (P1). The first real
communication only happens after qualification.
"""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.agents.registry import register_agent


class SDRAgent(BaseAgent):
    name = "sdr"

    def role_instructions(self, ctx: AgentContext) -> str:
        return (
            "You intake a brand-new lead. Read the entry channel and any data "
            "provided, then assign an INITIAL temperature (cold/warm/hot) as a "
            "first guess from explicit signals only. Do NOT write a message to the "
            "lead — your job ends by handing off to qualification. Never pass a "
            "lead without an initial temperature."
        )

    def output_contract(self) -> str:
        return (
            "Return JSON: {initial_temperature: 'cold'|'warm'|'hot', "
            "rationale: string, needs_qualification: boolean, facts: object}."
        )

    def shape_result(self, ctx: AgentContext, data: dict) -> AgentResult:
        temp = data.get("initial_temperature", "warm")
        return AgentResult(
            agent=self.name,
            output=data,
            temperature=temp,
            needs_qualification=bool(data.get("needs_qualification", True)),
            facts=data.get("facts", {}),
            # NO messages — P1.
        )


register_agent(SDRAgent())
