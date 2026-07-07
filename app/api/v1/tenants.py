from __future__ import annotations

import secrets

from fastapi import APIRouter, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession
from app.core.exceptions import NotFoundError
from app.core.security import generate_api_key
from app.models.tenant import Tenant, TenantApiKey
from app.schemas.tenant import TenantCreate, TenantCreated
from app.services.niche_service import NicheService

router = APIRouter()


@router.post("", response_model=TenantCreated, status_code=status.HTTP_201_CREATED)
async def create_tenant(body: TenantCreate, session: DbSession) -> TenantCreated:
    """Provision a new client as an instance of a niche (P2) and issue its first
    API key (shown once).

    Slug creation is collision-proof: the frontend derives the slug from the
    user id (``t-<uid8>``), so a leftover/orphan tenant from a previous failed
    provisioning attempt would otherwise raise a UniqueViolation → opaque 500
    and trap onboarding. On collision we retry with a short random suffix inside
    a SAVEPOINT so the outer transaction stays usable.
    """
    niche = await NicheService(session).by_slug(body.niche_slug)
    if niche is None:
        raise NotFoundError(f"Unknown niche '{body.niche_slug}'")

    # P6/§04-01: el tenant nace SIN módulos. El Coach Agent los habilita recién
    # tras completar el diagnóstico del onboarding (POST /onboarding/diagnose).
    tenant: Tenant | None = None
    for attempt in range(6):
        slug = body.slug if attempt == 0 else f"{body.slug}-{secrets.token_hex(3)}"
        try:
            async with session.begin_nested():  # SAVEPOINT
                tenant = Tenant(name=body.name, slug=slug, niche_id=niche.id)
                session.add(tenant)
                await session.flush()
            break
        except IntegrityError:
            tenant = None  # slug ya tomado → reintentar con sufijo
    if tenant is None:
        raise NotFoundError("No se pudo generar un slug único para el tenant")

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
