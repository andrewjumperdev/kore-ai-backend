"""Orchestrator Agent (§04-ORQ) — supervisor.

Always-on supervisor of the whole chain. Given the current pipeline state and
metrics (§08), it produces a daily report, anomaly alerts, prioritization for
human closing, and recommended actions. The deterministic escalation RULES
(§05) live in app.orchestrator.rules; this agent provides the human-readable
synthesis and recommendations on top of them.
"""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.agents.registry import register_agent


class OrchestratorAgent(BaseAgent):
    name = "orchestrator"

    def role_instructions(self, ctx: AgentContext) -> str:
        return (
            "You are the supervisor of the agent chain. From the pipeline snapshot "
            "and metrics provided, produce: a concise daily report, anomaly alerts "
            "with specific recommended actions, and a prioritized list of leads for "
            "human closing. Be decisive and specific; reference concrete numbers."
        )

    def output_contract(self) -> str:
        return (
            "Return JSON: {report: string, "
            "alerts: {metric: string, issue: string, action: string}[], "
            "priorities: {contact_id: string, why: string}[], "
            "recommendations: string[]}."
        )

    def shape_result(self, ctx: AgentContext, data: dict) -> AgentResult:
        return AgentResult(agent=self.name, output=data, reply=data.get("report"))


register_agent(OrchestratorAgent())
