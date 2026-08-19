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
from app.core.exceptions import KoreError, RateLimitExceeded
from app.core.logging import configure_logging, get_logger, request_id_ctx
from app.core.observability import init_sentry
from app.core.ratelimit import client_ip, hit
from app.core.redis import redis_client

# Register event subscribers on import so the API process can fan out too.
import app.events.handlers  # noqa: F401

log = get_logger("app")

# Rutas que el límite global por IP no debe tocar: el health check lo golpea el
# orquestador/monitor a alta frecuencia y no cuesta nada servirlo.
_UNLIMITED_PATHS = frozenset({"/health", "/health/ready"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.debug)
    init_sentry()
    log.info("app.startup", env=settings.env, model=settings.llm_model)
    try:
        await redis_client.ping()
    except Exception as exc:  # surface, don't crash boot in dev
        log.warning("redis.unavailable", error=str(exc))
    yield
    await redis_client.aclose()
    log.info("app.shutdown")


def create_app() -> FastAPI:
    # En producción el esquema de la API no se publica: describe cada endpoint
    # y cada header de auth para quien quiera sondearlos.
    docs = settings.serve_docs
    app = FastAPI(
        title=settings.project_name,
        version="0.1.0",
        description="Kore AI — The Operating System for Growth",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
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

    @app.middleware("http")
    async def global_rate_limit(request: Request, call_next):
        """Techo por IP para toda la API. Los límites finos (por tenant, por
        endpoint caro) se aplican en sus rutas; esto solo frena el abuso bruto."""
        if request.url.path not in _UNLIMITED_PATHS:
            try:
                await hit(f"global:{client_ip(request)}", limit=settings.rate_limit_per_minute)
            except RateLimitExceeded as exc:
                return _rate_limit_response(exc)
        return await call_next(request)

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(_: Request, exc: RateLimitExceeded):
        return _rate_limit_response(exc)

    @app.exception_handler(KoreError)
    async def kore_error_handler(_: Request, exc: KoreError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @app.get("/health", tags=["meta"])
    async def health():
        return {"status": "ok", "service": settings.project_name}

    @app.get("/health/ready", tags=["meta"])
    async def ready():
        """Readiness: comprueba las dependencias de las que el proceso no puede
        prescindir. Es la que debe mirar un orquestador antes de mandar tráfico."""
        checks: dict[str, str] = {}
        try:
            await redis_client.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = f"error: {exc}"

        from sqlalchemy import text

        from app.core.database import engine

        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["postgres"] = "ok"
        except Exception as exc:
            checks["postgres"] = f"error: {exc}"

        healthy = all(v == "ok" for v in checks.values())
        return JSONResponse(
            status_code=200 if healthy else 503,
            content={"status": "ok" if healthy else "degraded", "checks": checks},
        )

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


def _rate_limit_response(exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        headers={"Retry-After": str(exc.retry_after)},
    )


app = create_app()
