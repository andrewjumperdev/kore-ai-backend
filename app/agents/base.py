"""BaseAgent — the lightweight, niche-aware agent contract.

run() is a template method:
  1. pull the relevant memory block (short + long + semantic),
  2. build a niche-aware system + user prompt (P2/P8),
  3. get structured JSON from the LLM,
  4. let the subclass shape it into an AgentResult with explicit side-effect
     intents: messages, temperature, escalations, modules, facts.

The runner — not the agent — decides what is allowed to actually happen
(P1/P3/P6 guards, sending vs. escalating). Agents stay pure and testable.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.agents.context import AgentContext
from app.core.enums import EscalationReason
from app.core.logging import get_logger

log = get_logger("agent")


@dataclass
class OutboundMessage:
    channel: str
    body: str
    to: str | None = None


@dataclass
class EscalationIntent:
    reason: EscalationReason
    title: str
    executive_summary: str = ""
    payload: dict = field(default_factory=dict)


@dataclass
class AgentResult:
    agent: str
    output: dict = field(default_factory=dict)
    reply: str | None = None
    messages: list[OutboundMessage] = field(default_factory=list)
    temperature: str | None = None              # set by sdr/qualification
    needs_qualification: bool = False           # qualification couldn't classify
    escalations: list[EscalationIntent] = field(default_factory=list)
    modules_to_enable: list[str] = field(default_factory=list)  # coach
    facts: dict = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "output": self.output,
            "reply": self.reply,
            "temperature": self.temperature,
            "needs_qualification": self.needs_qualification,
            "modules_to_enable": self.modules_to_enable,
            "facts": self.facts,
            "messages": [m.__dict__ for m in self.messages],
            "escalations": [
                {"reason": str(e.reason), "title": e.title} for e in self.escalations
            ],
        }


class BaseAgent(ABC):
    name: str = "base"

    @abstractmethod
    def role_instructions(self, ctx: AgentContext) -> str: ...

    def output_contract(self) -> str:
        return "Return a single JSON object with the keys described above."

    async def build_user_prompt(self, ctx: AgentContext) -> str:
        mem = await ctx.memory.build_context_block(
            conversation_id=ctx.conversation_id,
            contact_id=str(ctx.contact_id) if ctx.contact_id else None,
            query=ctx.user_message,
        )
        return (
            f"NICHE: {ctx.niche_slug}\n"
            f"NICHE CONFIG:\n{ctx.niche_config}\n\n"
            f"BUSINESS PROFILE (diagnosis):\n{ctx.business_profile}\n\n"
            f"CONTACT TEMPERATURE: {ctx.current_temperature}\n\n"
            f"MEMORY:\n{mem}\n\n"
            f"TRIGGER / INBOUND:\n{ctx.input}\n\n"
            f"{self.output_contract()}\n"
            'Always include "_niche": "<niche slug>" in your JSON to confirm you '
            "operated within the niche frame. Never assert anything outside the "
            "niche boundaries; if unsure, set \"needs_human\": true."
        )

    def system_prompt(self, ctx: AgentContext) -> str:
        boundaries = ctx.niche_config.get("prompt_boundaries", "")
        return (
            f"You are the {self.name} agent inside KORE IA, an automated commercial "
            f"infrastructure that sells turnkey, niche-specific growth systems. You "
            f"operate strictly within the '{ctx.niche_slug}' niche. Be concise and "
            f"human. Never promise 100% autonomy — the promise is productivity "
            f"multiplication (P7). Never invent facts outside the niche frame (P8).\n"
            f"NICHE BOUNDARIES: {boundaries}\n\n"
            f"{self.role_instructions(ctx)}"
        )

    async def run(self, ctx: AgentContext) -> AgentResult:
        system = self.system_prompt(ctx)
        user = await self.build_user_prompt(ctx)
        llm_result = await ctx.llm.complete_json(system=system, user=user)
        result = self.shape_result(ctx, llm_result.data)
        # Ensure niche echo is present for the orchestrator's P2/P8 check.
        result.output.setdefault("_niche", llm_result.data.get("_niche", ctx.niche_slug))
        result.input_tokens = llm_result.input_tokens
        result.output_tokens = llm_result.output_tokens
        log.info("agent.run", agent=self.name, temperature=result.temperature)
        return result

    @abstractmethod
    def shape_result(self, ctx: AgentContext, data: dict) -> AgentResult: ...
