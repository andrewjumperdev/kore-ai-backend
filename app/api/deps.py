"""Request dependencies: resolve + bind the tenant, expose a DB session.

Authentication accepts either a tenant API key (``Authorization: Bearer
kore_…``) or a user JWT. Both resolve to a tenant_id which is bound into the
ContextVar so every downstream query and emitted event is automatically scoped.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import set_current_tenant
from app.core.database import get_db
from app.core.exceptions import AuthenticationError
from app.core.logging import tenant_id_ctx
from app.core.security import decode_access_token, hash_api_key
from app.models.tenant import TenantApiKey

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

    if token.startswith("kore_"):
        tenant_id = await _tenant_from_api_key(session, token)
    else:
        try:
            tenant_id = UUID(decode_access_token(token)["tid"])
        except Exception as exc:
            raise AuthenticationError("Invalid token") from exc

    set_current_tenant(tenant_id)
    tenant_id_ctx.set(str(tenant_id))
    return tenant_id


TenantId = Annotated[UUID, Depends(get_tenant_id)]
