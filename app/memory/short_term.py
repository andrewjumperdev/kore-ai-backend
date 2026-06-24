"""Short-term / working memory in Redis.

Holds the rolling conversation window and ephemeral agent scratchpad with a
TTL. Fast, cheap, and disposable — anything that must survive goes to
long-term or semantic memory.
"""
from __future__ import annotations

import json
from uuid import UUID

from app.core.redis import redis_client

_WINDOW = 20          # messages kept hot per conversation
_TTL_SECONDS = 60 * 60 * 24  # 24h


def _key(tenant_id: UUID, conversation_id: UUID) -> str:
    return f"stm:{tenant_id}:conv:{conversation_id}"


class ShortTermMemory:
    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id

    async def append_turn(self, conversation_id: UUID, role: str, content: str) -> None:
        key = _key(self.tenant_id, conversation_id)
        await redis_client.rpush(key, json.dumps({"role": role, "content": content}))
        await redis_client.ltrim(key, -_WINDOW, -1)
        await redis_client.expire(key, _TTL_SECONDS)

    async def recent_turns(self, conversation_id: UUID) -> list[dict]:
        raw = await redis_client.lrange(_key(self.tenant_id, conversation_id), 0, -1)
        return [json.loads(r) for r in raw]

    async def set_scratch(self, conversation_id: UUID, data: dict) -> None:
        await redis_client.set(
            f"{_key(self.tenant_id, conversation_id)}:scratch",
            json.dumps(data),
            ex=_TTL_SECONDS,
        )

    async def get_scratch(self, conversation_id: UUID) -> dict:
        raw = await redis_client.get(f"{_key(self.tenant_id, conversation_id)}:scratch")
        return json.loads(raw) if raw else {}
