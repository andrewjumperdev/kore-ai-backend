"""Shared async Redis client (cache, sessions, short-term memory, queue state)."""
from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import settings

_pool = aioredis.ConnectionPool.from_url(
    settings.redis_url,
    decode_responses=True,
    max_connections=50,
)


def get_redis() -> aioredis.Redis:
    """Return a client bound to the shared connection pool."""
    return aioredis.Redis(connection_pool=_pool)


redis_client = get_redis()
