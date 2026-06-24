"""Niche service — the replicable model. Andrew builds a niche ONCE; this
service resolves the niche config that calibrates every agent for a client.

The config schema (stored in Niche.config) is intentionally open JSON so a niche
can be extended without migrations, but these keys are the contract agents rely
on. ``NICHE_CONFIG_KEYS`` documents and validates the minimum shape.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Module
from app.models.niche import Niche

NICHE_CONFIG_KEYS = (
    "coach_questions",        # list[str] — diagnostic questions
    "qualification_signals",  # {hot: [...], warm: [...], cold: [...]}
    "followup_sequences",     # {hot: [...], warm: [...], cold: [...]}
    "proposal_template",      # {structure, positioning, ...}
    "content_templates",      # {post, email, script}
    "prompt_boundaries",      # str — what the model may/may not assert (P8)
    "default_modules",        # list[Module]
    "tone",                   # str
)


def default_config() -> dict:
    return {
        "coach_questions": [],
        "qualification_signals": {"hot": [], "warm": [], "cold": []},
        "followup_sequences": {"hot": [1, 2], "warm": [2, 5], "cold": [7, 21]},
        "proposal_template": {},
        "content_templates": {},
        "prompt_boundaries": "No inventar datos fuera del marco del nicho; "
        "ante falta de información, solicitar o escalar al humano.",
        "default_modules": [m.value for m in Module],
        "tone": "profesional y directo",
    }


class NicheService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, niche_id: UUID) -> Niche | None:
        return await self.session.get(Niche, niche_id)

    async def by_slug(self, slug: str) -> Niche | None:
        return await self.session.scalar(select(Niche).where(Niche.slug == slug))

    async def upsert(
        self, *, slug: str, name: str, status: str, priority: int, config: dict
    ) -> Niche:
        niche = await self.by_slug(slug)
        merged = {**default_config(), **config}
        if niche is None:
            niche = Niche(
                slug=slug, name=name, status=status, priority=priority, config=merged
            )
            self.session.add(niche)
        else:
            niche.name = name
            niche.status = status
            niche.priority = priority
            niche.config = merged
        await self.session.flush()
        return niche
