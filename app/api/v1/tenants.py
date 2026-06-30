from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import DbSession
from app.core.exceptions import NotFoundError
from app.core.enums import Module
from app.core.security import generate_api_key
from app.models.tenant import Tenant, TenantApiKey
from app.schemas.tenant import TenantCreate, TenantCreated
from app.services.niche_service import NicheService

router = APIRouter()


@router.post("", response_model=TenantCreated, status_code=status.HTTP_201_CREATED)
async def create_tenant(body: TenantCreate, session: DbSession) -> TenantCreated:
    """Provision a new client as an instance of a niche (P2) and issue its first
    API key (shown once)."""
    niche = await NicheService(session).by_slug(body.niche_slug)
    if niche is None:
        raise NotFoundError(f"Unknown niche '{body.niche_slug}'")

    # MVP: habilitamos todos los módulos por defecto para que los agentes
    # (content, etc.) operen sin requerir antes el diagnóstico del Coach. El Coach
    # los re-calibra cuando corre.
    tenant = Tenant(
        name=body.name,
        slug=body.slug,
        niche_id=niche.id,
        enabled_modules=[m.value for m in Module],
    )
    session.add(tenant)
    await session.flush()

    raw_key, hashed = generate_api_key()
    session.add(TenantApiKey(tenant_id=tenant.id, hashed_key=hashed, prefix=raw_key[:12]))
    await session.flush()

    return TenantCreated(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        niche_id=tenant.niche_id,
        is_active=tenant.is_active,
        enabled_modules=tenant.enabled_modules,
        diagnosis_completed_at=tenant.diagnosis_completed_at,
        activated_at=tenant.activated_at,
        business_profile=tenant.business_profile,
        api_key=raw_key,
    )
