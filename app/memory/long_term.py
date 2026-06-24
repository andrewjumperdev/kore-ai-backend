"""Long-term memory in Postgres — durable structured facts (key/value JSON),
queried by scope + key rather than similarity. Writes are idempotent upserts on
(tenant_id, scope, scope_id, key)."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import LongTermMemory

_GLOBAL = "global"


class LongTermMemoryStore:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    async def remember(self, scope: str, scope_id: str | None, key: str, value: dict) -> None:
        sid = scope_id or _GLOBAL
        stmt = (
            insert(LongTermMemory)
            .values(
                tenant_id=self.tenant_id, scope=scope, scope_id=sid, key=key, value=value
            )
            .on_conflict_do_update(
                constraint="uq_ltm_scope_key",
                set_={"value": value},
            )
        )
        await self.session.execute(stmt)

    async def recall(self, scope: str, scope_id: str | None) -> dict[str, dict]:
        rows = await self.session.scalars(
            select(LongTermMemory).where(
                LongTermMemory.tenant_id == self.tenant_id,
                LongTermMemory.scope == scope,
                LongTermMemory.scope_id == (scope_id or _GLOBAL),
            )
        )
        return {row.key: row.value for row in rows}
