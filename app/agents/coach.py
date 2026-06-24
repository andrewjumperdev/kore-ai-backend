"""Coach Agent (§04-01) — diagnosis. The single point where a client's system
is configured. Uses the niche's coach_questions to diagnose the business, then
produces the business profile, strategy, and the set of modules to enable.

CRITICAL RULE: never enables modules without completing the diagnosis.
"""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.agents.registry import register_agent
from app.core.enums import Module


class AgentCoach(BaseAgent):
    name = "coach"

    def role_instructions(self, ctx: AgentContext) -> str:
        questions = ctx.niche_config.get("coach_questions", [])
        return (
            "You onboard a new client by DIAGNOSING their business using the "
            f"niche's diagnostic questions: {questions}. From their answers, infer "
            "a complete, ready-to-use growth configuration for THIS niche. Be "
            "specific: concrete ICP, sharp value props, real objections + rebuttals. "
            "Then decide which system modules to enable for this client."
        )

    def output_contract(self) -> str:
        return (
            "Return JSON: {industry: string, "
            "icp: {description: string, pains: string[], triggers: string[]}, "
            "value_props: string[], "
            "objections: {objection: string, rebuttal: string}[], "
            "strategy: string, summary: string, "
            "diagnosis_complete: boolean, "
            f"enable_modules: string[] (subset of {[m.value for m in Module]})}}."
        )

    def shape_result(self, ctx: AgentContext, data: dict) -> AgentResult:
        # Only enable modules if the diagnosis is complete (CRITICAL RULE).
        complete = bool(data.get("diagnosis_complete", True))
        modules = (
            data.get("enable_modules")
            or ctx.niche_config.get("default_modules", [m.value for m in Module])
        ) if complete else []
        return AgentResult(
            agent=self.name,
            output=data,
            reply=data.get("summary"),
            facts={"business_profile": data},
            modules_to_enable=modules,
        )


register_agent(AgentCoach())
