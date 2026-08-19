"""Request dependencies: resolve + bind the tenant, expose a DB session.

La autenticación de tenant es **una sola**: ``Authorization: Bearer kore_…``,
la API key del tenant. Resuelve a un tenant_id que se bindea al ContextVar, así
toda query y todo evento emitido río abajo quedan scopeados solos.

Hay dos autorizaciones más, deliberadamente separadas de la del tenant:

* ``ProvisioningAuth`` — alta de tenants. Solo la conoce el BFF del frontend.
* ``AdminAuth`` — operaciones de operador (cobros, activaciones). **Un tenant
  nunca debe poder invocarlas con su propia API key**, por eso no derivan de
  ``get_tenant_id``.
"""
from __future__ import annotations

import secrets
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.context import set_current_tenant
from app.core.database import get_db
from app.core.exceptions import AuthenticationError, ConfigurationError
from app.core.logging import get_logger, tenant_id_ctx
from app.core.security import hash_api_key
from app.models.tenant import TenantApiKey

log = get_logger("auth")

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def _tenant_from_api_key(session: AsyncSession, raw_key: str) -> UUID:
    row = await session.scalar(
        select(TenantApiKey).where(
            TenantApiKey.hashed_key == hash_api_key(raw_key),
            TenantApiKey.revoked.is_(False),
        )
    )
    if row is None:
        raise AuthenticationError("Invalid API key")
    return row.tenant_id


async def get_tenant_id(
    session: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> UUID:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()

    if not token.startswith("kore_"):
        raise AuthenticationError("Invalid token")
    tenant_id = await _tenant_from_api_key(session, token)

    set_current_tenant(tenant_id)
    tenant_id_ctx.set(str(tenant_id))
    return tenant_id


TenantId = Annotated[UUID, Depends(get_tenant_id)]


# ── Secretos de servicio (no son credenciales de tenant) ─────────────

def _require_shared_secret(provided: str | None, expected: str, *, what: str) -> None:
    """Compara en tiempo constante y falla *cerrado* si no hay secreto seteado.

    En desarrollo, sin secreto configurado, deja pasar con un warning para no
    entorpecer el laburo local; en producción la validación de config ya impide
    arrancar sin él, y este chequeo es la segunda red.
    """
    if not expected:
        if settings.is_production:
            raise ConfigurationError(f"Falta configurar el secreto de {what}")
        log.warning("auth.shared_secret_unset_dev", what=what)
        return
    if not provided or not secrets.compare_digest(provided, expected):
        log.warning("auth.shared_secret_invalid", what=what)
        raise AuthenticationError(f"Invalid {what} credentials")


async def require_provisioning_secret(
    x_provisioning_secret: Annotated[str | None, Header()] = None,
) -> None:
    """Autoriza el alta de tenants. Sin esto, cualquiera se autoprovisiona un
    tenant con API key válida y gasta nuestro presupuesto de LLM."""
    _require_shared_secret(
        x_provisioning_secret, settings.provisioning_secret, what="provisioning"
    )


async def require_admin(
    x_admin_key: Annotated[str | None, Header()] = None,
) -> None:
    """Autoriza operaciones de operador. Siempre fail-closed en producción."""
    _require_shared_secret(x_admin_key, settings.admin_api_key, what="admin")


ProvisioningAuth = Depends(require_provisioning_secret)
AdminAuth = Depends(require_admin)
