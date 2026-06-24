"""Dramatiq broker wired to Redis (lighter than Celery, no extra infra).

A small ``run_async`` shim lets us call the async domain layer from Dramatiq's
threaded actors with one event loop per task invocation.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Coroutine
from typing import TypeVar

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import AgeLimit, Retries, ShutdownNotifications, TimeLimit

from app.core.config import settings

redis_broker = RedisBroker(
    url=settings.redis_url,
    middleware=[
        AgeLimit(),
        TimeLimit(time_limit=120_000),  # 2 min hard cap per task
        ShutdownNotifications(),
        Retries(max_retries=3, min_backoff=1_000, max_backoff=60_000),
    ],
)
dramatiq.set_broker(redis_broker)

T = TypeVar("T")


def run_async(coro: Coroutine[None, None, T] | Awaitable[T]) -> T:
    return asyncio.run(coro)  # type: ignore[arg-type]
