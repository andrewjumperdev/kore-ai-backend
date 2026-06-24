"""Proposal Agent (§04-05) — propuesta.

Prepares a tailored proposal that ALWAYS connects to the problem detected in the
Coach diagnosis (P6 — no diagnosis, no proposal; enforced by the runner). It does
NOT send or close: it prepares the proposal + an executive summary and escalates
to a human closing meeting (P3).
"""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent, EscalationIntent
from app.agents.registry import register_agent
from app.core.enums import EscalationReason


class ProposalAgent(BaseAgent):
    name = "proposal"

    def role_instructions(self, ctx: AgentContext) -> str:
        template = ctx.niche_config.get("proposal_template", {})
        return (
            "You prepare a tailored sales proposal that connects directly to the "
            "specific problem found in the diagnosis. Use the niche proposal "
            f"template: {template}. Be specific on scope and outcomes; price with "
            "clear tiers. You do NOT close — you prepare and hand off to a human."
        )

    def output_contract(self) -> str:
        return (
            "Return JSON: {title: string, summary: string, scope: string[], "
            "pricing: {tier: string, price: string, includes: string[]}[], "
            "terms: string, executive_summary: string, meeting_agenda: string[]}."
        )

    def shape_result(self, ctx: AgentContext, data: dict) -> AgentResult:
        # P3 — never auto-send. Always escalate for human close.
        return AgentResult(
            agent=self.name,
            output=data,
            facts={"last_proposal": {"title": data.get("title"), "pricing": data.get("pricing")}},
            escalations=[
                EscalationIntent(
                    reason=EscalationReason.PROPOSAL_REVIEW,
                    title=f"Propuesta lista para cierre: {data.get('title', 'propuesta')}",
                    executive_summary=data.get("executive_summary", data.get("summary", "")),
                    payload={
                        "proposal": data,
                        "contact_id": str(ctx.contact_id) if ctx.contact_id else None,
                    },
                )
            ],
        )


register_agent(ProposalAgent())
