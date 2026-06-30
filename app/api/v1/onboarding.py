"""Onboarding = elegir nicho + diagnóstico del Coach (§03, §04-01).

El cliente nuevo ELIGE su nicho; eso define las preguntas del Coach. Responde, el
Coach arma el perfil + estrategia y HABILITA los módulos (P6: sin diagnóstico no
hay módulos). Es el único punto donde se configura el cliente.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.runner import AgentRunner
from app.api.deps import DbSession, TenantId
from app.core.exceptions import NotFoundError, PolicyViolation
from app.models.niche import Niche
from app.models.tenant import Tenant
from app.services.niche_service import NicheService

router = APIRouter()

# Nichos internos que el cliente NO elige (caso de uso propio de Andrew).
_INTERNAL_NICHES = {"plaud-ar"}


class NicheBrief(BaseModel):
    slug: str
    name: str


class OnboardingInfo(BaseModel):
    niche_slug: str | None
    niche_name: str | None
    questions: list[str]
    diagnosis_completed: bool
    enabled_modules: list[str]
    niches: list[NicheBrief]  # nichos seleccionables


class SelectNicheIn(BaseModel):
    niche_slug: str


class DiagnoseIn(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)


class DiagnoseOut(BaseModel):
    summary: str | None = None
    strategy: str | None = None
    industry: str | None = None
    enabled_modules: list[str] = Field(default_factory=list)


async def _build_info(session, tenant: Tenant) -> OnboardingInfo:
    niche = await NicheService(session).get(tenant.niche_id) if tenant.niche_id else None
    questions = list((niche.config or {}).get("coach_questions", [])) if niche else []
    rows = await session.scalars(
        select(Niche).where(Niche.slug.notin_(_INTERNAL_NICHES)).order_by(Niche.priority)
    )
    niches = [NicheBrief(slug=n.slug, name=n.name) for n in rows]
    return OnboardingInfo(
        niche_slug=niche.slug if niche else None,
        niche_name=niche.name if niche else None,
        questions=questions,
        diagnosis_completed=tenant.diagnosis_completed_at is not None,
        enabled_modules=tenant.enabled_modules or [],
        niches=niches,
    )


@router.get("", response_model=OnboardingInfo)
async def onboarding_info(tenant_id: TenantId, session: DbSession) -> OnboardingInfo:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found")
    return await _build_info(session, tenant)


@router.post("/niche", response_model=OnboardingInfo)
async def select_niche(body: SelectNicheIn, tenant_id: TenantId, session: DbSession) -> OnboardingInfo:
    """El cliente elige su nicho → define las preguntas del Coach."""
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found")
    if tenant.diagnosis_completed_at is not None:
        raise PolicyViolation("El diagnóstico ya fue completado; el nicho no se puede cambiar.")
    niche = await NicheService(session).by_slug(body.niche_slug)
    if niche is None or niche.slug in _INTERNAL_NICHES:
        raise NotFoundError(f"Unknown niche '{body.niche_slug}'")
    tenant.niche_id = niche.id
    await session.flush()
    return await _build_info(session, tenant)


@router.post("/diagnose", response_model=DiagnoseOut)
async def diagnose(body: DiagnoseIn, tenant_id: TenantId, session: DbSession) -> DiagnoseOut:
    """Corre el Coach con las respuestas. El runner habilita los módulos y marca
    diagnosis_completed_at."""
    message = "Respuestas del diagnóstico de onboarding:\n" + "\n".join(
        f"- {q}: {a}" for q, a in body.answers.items() if a
    )
    run = await AgentRunner(session, tenant_id).run(
        "coach", {"message": message, "answers": body.answers}
    )
    out = run.output or {}
    data = out.get("output", {}) if isinstance(out.get("output"), dict) else {}

    tenant = await session.get(Tenant, tenant_id)
    return DiagnoseOut(
        summary=data.get("summary") or out.get("reply"),
        strategy=data.get("strategy"),
        industry=data.get("industry"),
        enabled_modules=(tenant.enabled_modules or []) if tenant else [],
    )
