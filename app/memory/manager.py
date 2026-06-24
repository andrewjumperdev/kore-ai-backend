"""Unified memory facade handed to every agent. Combines short-term (Redis),
long-term (Postgres) and semantic (pgvector) into one ergonomic surface."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.long_term import LongTermMemoryStore
from app.memory.semantic import SemanticMemoryStore
from app.memory.short_term import ShortTermMemory


class MemoryManager:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.short = ShortTermMemory(tenant_id)
        self.long = LongTermMemoryStore(session, tenant_id)
        self.semantic = SemanticMemoryStore(session, tenant_id)

    async def build_context_block(
        self, *, conversation_id: UUID | None, contact_id: str | None, query: str
    ) -> dict:
        """Assemble the memory the agent should see for this turn."""
        recent = (
            await self.short.recent_turns(conversation_id) if conversation_id else []
        )
        facts = await self.long.recall("contact", contact_id) if contact_id else {}
        relevant = await self.semantic.search(query, limit=4) if query else []
        return {
            "recent_turns": recent,
            "known_facts": facts,
            "relevant_memory": [
                {"content": m.content, "distance": round(d, 4)} for m, d in relevant
            ],
        }
