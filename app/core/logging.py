"""Structured JSON logging with tenant/request correlation."""
from __future__ import annotations

import logging
from contextvars import ContextVar

import structlog

# Bound per-request; surfaces in every log line emitted during the request.
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
tenant_id_ctx: ContextVar[str | None] = ContextVar("tenant_id", default=None)


def _inject_context(_, __, event_dict: dict) -> dict:
    if rid := request_id_ctx.get():
        event_dict["request_id"] = rid
    if tid := tenant_id_ctx.get():
        event_dict["tenant_id"] = tid
    return event_dict


def configure_logging(debug: bool = False) -> None:
    logging.basicConfig(format="%(message)s", level=logging.DEBUG if debug else logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _inject_context,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer() if debug else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if debug else logging.INFO
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "kore") -> structlog.BoundLogger:
    return structlog.get_logger(name)
