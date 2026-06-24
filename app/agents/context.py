"""Everything an agent needs to do its job, assembled by the runner. The niche
config (P2/P8) is first-class: agents always operate niche-aware."""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import LLMClient, llm
from app.core.enums import Temperature
from app.memory.manager import MemoryManager


@dataclass
class AgentContext:
    tenant_id: UUID
    session: AsyncSession
    memory: MemoryManager
    business_profile: dict = field(default_factory=dict)
    # Niche template config (coach_questions, qualification_signals, sequences,
    # prompt_boundaries…). Mandatory for every business agent.
    niche_slug: str | None = None
    niche_config: dict = field(default_factory=dict)
    contact_id: UUID | None = None
    conversation_id: UUID | None = None
    current_temperature: str = Temperature.UNSET
    input: dict = field(default_factory=dict)
    llm: LLMClient = llm

    @property
    def user_message(self) -> str:
        return self.input.get("message", "") or self.input.get("trigger", "")
