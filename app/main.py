"""FastAPI application bootstrap.

Wires logging, the v1 router, a domain-exception handler, request/tenant
correlation, and lifecycle hooks. The ASGI app is created by ``create_app()``
so tests can build isolated instances.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import KoreError
from app.core.logging import configure_logging, get_logger, request_id_ctx
from app.core.redis import redis_client

# Register event subscribers on import so the API process can fan out too.
import app.events.handlers  # noqa: F401

log = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.debug)
    log.info("app.startup", env=settings.env, model=settings.llm_model)
    try:
        await redis_client.ping()
    except Exception as exc:  # surface, don't crash boot in dev
        log.warning("redis.unavailable", error=str(exc))
    yield
    await redis_client.aclose()
    log.info("app.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.project_name,
        version="0.1.0",
        description="Kore AI — The Operating System for Growth",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not settings.is_production else [],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def correlation(request: Request, call_next):
        rid = request.headers.get("x-request-id", str(uuid.uuid4()))
        request_id_ctx.set(rid)
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    @app.exception_handler(KoreError)
    async def kore_error_handler(_: Request, exc: KoreError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @app.get("/health", tags=["meta"])
    async def health():
        return {"status": "ok", "service": settings.project_name}

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
