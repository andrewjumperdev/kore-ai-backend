"""Dramatiq broker wired to Redis (lighter than Celery, no extra infra).

``run_async`` corre las coroutines del dominio en UN ÚNICO event loop persistente
(en su propio thread). Es clave: si usáramos ``asyncio.run`` por task, cada task
crearía y CERRARÍA un loop nuevo, y los clientes async globales (pool de Redis del
event bus, httpx del LLM) quedarían atados a un loop cerrado → "Event loop is
closed". Con un loop persistente, esos clientes siguen válidos entre tasks.
"""
from __future__ import annotations

import asyncio
import threading
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

_worker_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _worker_loop
    with _loop_lock:
        if _worker_loop is None or _worker_loop.is_closed():
            _worker_loop = asyncio.new_event_loop()
            threading.Thread(
                target=_worker_loop.run_forever, daemon=True, name="kore-async-loop"
            ).start()
    return _worker_loop


def run_async(coro: Coroutine[None, None, T] | Awaitable[T]) -> T:
    """Ejecuta `coro` en el loop persistente del worker y espera el resultado.
    Thread-safe: los hilos de Dramatiq la pueden llamar en paralelo."""
    return asyncio.run_coroutine_threadsafe(coro, _ensure_loop()).result()  # type: ignore[arg-type]
