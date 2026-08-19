from __future__ import annotations

import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.api.deps import AdminAuth, DbSession, ProvisioningAuth
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.ratelimit import RateLimit
from app.core.security import generate_api_key
from app.models.tenant import Tenant, TenantApiKey
from app.schemas.tenant import TenantCreate, TenantCreated, TenantOut
from app.services.niche_service import NicheService

router = APIRouter()


@router.post(
    "",
    response_model=TenantCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        ProvisioningAuth,
        Depends(
            RateLimit(
                "tenants:create",
                settings.rate_limit_tenant_create_per_hour,
                window=3600,
            )
        ),
    ],
)
async def create_tenant(body: TenantCreate, session: DbSession) -> TenantCreated:
    """Provision a new client as an instance of a niche (P2) and issue its first
    API key (shown once).

    **Autenticado con el secreto de provisioning** (header
    ``x-provisioning-secret``), que solo conoce el BFF del frontend: este
    endpoint emite una API key válida, así que abierto sería una puerta directa
    a gastar nuestro presupuesto de LLM.

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


class TenantActiveIn(BaseModel):
    tenant_id: UUID
    is_active: bool


@router.post("/admin/active", response_model=TenantOut, dependencies=[AdminAuth])
async def set_tenant_active(body: TenantActiveIn, session: DbSession) -> TenantOut:
    """Enciende o apaga TODA la cuenta de un cliente.

    Es el freno de último recurso: con `is_active=False` ningún agente corre
    para ese tenant (el guard vive en app.orchestrator.policy). Sirve para
    cortar por lo sano si el sistema se está portando mal con los clientes
    finales de alguien, sin tener que apagar la plataforma entera.

    Operación de operador, no del cliente: un tenant no puede reactivarse solo.
    """
    tenant = await session.get(Tenant, body.tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found")
    tenant.is_active = body.is_active
    await session.flush()
    return TenantOut.model_validate(tenant)
