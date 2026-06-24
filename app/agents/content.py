"""Content Agent (Capa 03) — genera publicaciones, emails y scripts.

Generates niche-tailored drafts from the niche content templates. Per P3, it
NEVER publishes authority/conversion content on its own — it prepares drafts and
escalates them for human review.
"""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent, EscalationIntent
from app.agents.registry import register_agent
from app.core.enums import EscalationReason


class ContentAgent(BaseAgent):
    name = "content"

    def role_instructions(self, ctx: AgentContext) -> str:
        templates = ctx.niche_config.get("content_templates", {})
        return (
            "You produce marketing content (posts, emails, scripts) tailored to the "
            f"niche using these templates: {templates}. Match the niche tone and "
            "audience. You PREPARE drafts only — you never publish; a human reviews "
            "and approves authority/conversion content first (P3)."
        )

    def output_contract(self) -> str:
        return (
            "Return JSON: {content_type: 'post'|'email'|'script', "
            "drafts: {channel: string, title: string, body: string}[], "
            "rationale: string}."
        )

    def shape_result(self, ctx: AgentContext, data: dict) -> AgentResult:
        drafts = data.get("drafts", [])
        return AgentResult(
            agent=self.name,
            output=data,
            escalations=[
                EscalationIntent(
                    reason=EscalationReason.CONTENT_REVIEW,
                    title=f"Contenido para revisión ({data.get('content_type', 'content')})",
                    executive_summary=data.get("rationale", ""),
                    payload={"drafts": drafts},
                )
            ],
        )


register_agent(ContentAgent())
