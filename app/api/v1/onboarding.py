"""Onboarding = elegir nicho + diagnóstico del Coach (§03, §04-01).

El cliente nuevo ELIGE su nicho; eso define las preguntas del Coach. Responde, el
Coach arma el perfil + estrategia y HABILITA los módulos (P6: sin diagnóstico no
hay módulos). Es el único punto donde se configura el cliente.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.runner import AgentRunner
from app.api.deps import DbSession, TenantId
from app.core.exceptions import NotFoundError, PolicyViolation
from app.core.logging import get_logger
from app.models.niche import Niche
from app.models.tenant import Tenant
from app.services.niche_service import NicheService

router = APIRouter()
log = get_logger("onboarding")

# Nichos internos que el cliente NO elige (caso de uso propio de Andrew).
_INTERNAL_NICHES = {"plaud-ar"}


class NicheBrief(BaseModel):
    slug: str
    name: str


class CoachQuestion(BaseModel):
    """Pregunta del diagnóstico con su ejemplo de respuesta.

    El ejemplo baja muchísimo la fricción: preguntas como "¿dónde se te escapan
    los seguimientos?" son claras para quien escribió el nicho y ambiguas para
    quien las lee por primera vez. Puede venir vacío — el nicho es la fuente y
    no todos tienen ejemplo cargado.
    """

    text: str
    example: str = ""


class OnboardingInfo(BaseModel):
    niche_slug: str | None
    niche_name: str | None
    questions: list[CoachQuestion]
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
    config = (niche.config or {}) if niche else {}
    # Los ejemplos se indexan por el texto de la pregunta, no por posición: si
    # alguien reordena las preguntas del nicho, el ejemplo simplemente falta en
    # vez de quedar pegado a la pregunta equivocada.
    examples = config.get("coach_examples", {})
    questions = [
        CoachQuestion(text=q, example=examples.get(q, ""))
        for q in config.get("coach_questions", [])
    ]
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
    try:
        run = await AgentRunner(session, tenant_id).run(
            "coach", {"message": message, "answers": body.answers}
        )
    except (PolicyViolation, NotFoundError):
        raise
    except Exception as exc:  # noqa: BLE001 — surfaceamos la causa real (no un 500 opaco)
        log.error("onboarding.diagnose_failed", error=str(exc), kind=type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail=f"El diagnóstico con IA falló: {type(exc).__name__}: {str(exc)[:220]}",
        ) from exc
    out = run.output or {}
    data = out.get("output", {}) if isinstance(out.get("output"), dict) else {}

    tenant = await session.get(Tenant, tenant_id)
    return DiagnoseOut(
        summary=data.get("summary") or out.get("reply"),
        strategy=data.get("strategy"),
        industry=data.get("industry"),
        enabled_modules=(tenant.enabled_modules or []) if tenant else [],
    )


@router.post("/reset", response_model=OnboardingInfo)
async def reset_diagnosis(tenant_id: TenantId, session: DbSession) -> OnboardingInfo:
    """Deja al cliente en condiciones de rehacer su diagnóstico.

    Hace falta para tres situaciones reales: el rubro elegido no era el correcto,
    el negocio cambió, o el perfil quedó corrupto. Sin esto el cliente quedaba en
    un callejón sin salida — ``select_niche`` bloquea el cambio de nicho una vez
    completado el diagnóstico, y no había forma de volver atrás.

    **Deja al sistema sin operar hasta que se rehaga el diagnóstico**: se vacían
    los módulos habilitados, así que los agentes dejan de responder (P6 y el gate
    de módulos). Es a propósito — seguir operando con una configuración que el
    propio cliente acaba de invalidar es peor que parar. Se revierte completando
    el onboarding de nuevo, que son dos minutos.

    El nicho se conserva para no obligar a reelegirlo, pero vuelve a ser
    editable: el gate de ``select_niche`` mira ``diagnosis_completed_at``.
    """
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found")

    tenant.diagnosis_completed_at = None
    tenant.business_profile = {}
    tenant.enabled_modules = []
    await session.flush()
    log.info("onboarding.reset", tenant_id=str(tenant_id))
    return await _build_info(session, tenant)
