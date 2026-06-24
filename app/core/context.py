"""Tenant context — the backbone of data isolation.

The active tenant is stored in a ContextVar set by middleware (HTTP) or
explicitly by tasks/handlers (background). Repositories and the event bus
read it to scope every query and every emitted event. Never trust a
tenant_id that arrives in a request body — only this value.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

from app.core.exceptions import TenantContextMissing

_current_tenant: ContextVar[UUID | None] = ContextVar("current_tenant", default=None)


def set_current_tenant(tenant_id: UUID | None) -> None:
    _current_tenant.set(tenant_id)


def get_current_tenant() -> UUID:
    tid = _current_tenant.get()
    if tid is None:
        raise TenantContextMissing("No tenant bound to the current execution context")
    return tid


def get_current_tenant_optional() -> UUID | None:
    return _current_tenant.get()


@contextmanager
def tenant_context(tenant_id: UUID):
    """Bind a tenant for the duration of a background unit of work."""
    token = _current_tenant.set(tenant_id)
    try:
        yield
    finally:
        _current_tenant.reset(token)
