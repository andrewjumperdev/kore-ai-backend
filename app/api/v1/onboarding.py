"""Onboarding = diagnóstico del Coach (§04-01).

El cliente nuevo responde las preguntas DEL NICHO; el Coach Agent las procesa,
arma el perfil del negocio + estrategia y HABILITA los módulos (P6: sin
diagnóstico no hay módulos). Es el único punto donde se configura el cliente.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agents.runner import AgentRunner
from app.api.deps import DbSession, TenantId
from app.core.exceptions import NotFoundError
from app.models.tenant import Tenant
from app.services.niche_service import NicheService

router = APIRouter()


class OnboardingInfo(BaseModel):
    niche_slug: str | None
    niche_name: str | None
    questions: list[str]
    diagnosis_completed: bool
    enabled_modules: list[str]


class DiagnoseIn(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)


class DiagnoseOut(BaseModel):
    summary: str | None = None
    strategy: str | None = None
    industry: str | None = None
    enabled_modules: list[str] = Field(default_factory=list)


@router.get("", response_model=OnboardingInfo)
async def onboarding_info(tenant_id: TenantId, session: DbSession) -> OnboardingInfo:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found")
    niche = await NicheService(session).get(tenant.niche_id) if tenant.niche_id else None
    questions = list((niche.config or {}).get("coach_questions", [])) if niche else []
    return OnboardingInfo(
        niche_slug=niche.slug if niche else None,
        niche_name=niche.name if niche else None,
        questions=questions,
        diagnosis_completed=tenant.diagnosis_completed_at is not None,
        enabled_modules=tenant.enabled_modules or [],
    )


@router.post("/diagnose", response_model=DiagnoseOut)
async def diagnose(body: DiagnoseIn, tenant_id: TenantId, session: DbSession) -> DiagnoseOut:
    """Corre el Coach con las respuestas del onboarding. El runner, como efecto,
    habilita los módulos y marca diagnosis_completed_at."""
    message = "Respuestas del diagnóstico de onboarding:\n" + "\n".join(
        f"- {q}: {a}" for q, a in body.answers.items() if a
    )
    run = await AgentRunner(session, tenant_id).run(
        "coach", {"message": message, "answers": body.answers}
    )
    out = run.output or {}
    data = out.get("output", {}) if isinstance(out.get("output"), dict) else {}

    tenant = await session.get(Tenant, tenant_id)  # recargar: el Coach ya habilitó módulos
    return DiagnoseOut(
        summary=data.get("summary") or out.get("reply"),
        strategy=data.get("strategy"),
        industry=data.get("industry"),
        enabled_modules=(tenant.enabled_modules or []) if tenant else [],
    )
