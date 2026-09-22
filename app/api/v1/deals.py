"""Oportunidades y empresas — la parte medible del CRM.

Un contacto caliente dice a quién atender ahora; una oportunidad dice cuánto
hay en juego y para cuándo. Sin esto el pipeline no se puede sumar, y es la
razón por la que Analytics estaba vacío.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import DbSession, TenantId
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.contact import Contact
from app.models.crm import CLOSED_STAGES, DEAL_STAGES, OPEN_STAGES, Company, Deal
from app.schemas.crm import (
    CompanyCreate,
    CompanyOut,
    DealCreate,
    DealOut,
    DealUpdate,
    PipelineOut,
    StageSummary,
)

router = APIRouter()
log = get_logger("deals")


def _name_key(name: str) -> str:
    """Clave de deduplicación: minúsculas y espacios colapsados. Evita que
    'ACME  S.A.' y 'acme s.a.' convivan como dos empresas."""
    return " ".join(name.lower().split())


def _check_stage(stage: str) -> None:
    if stage not in DEAL_STAGES:
        raise ValidationError(
            f"Etapa inválida: {stage}", details={"validas": list(DEAL_STAGES)}
        )


# ── Empresas ────────────────────────────────────────────────────────

@router.get("/companies", response_model=list[CompanyOut])
async def list_companies(
    tenant_id: TenantId, session: DbSession, limit: int = Query(default=200, le=500)
) -> list[CompanyOut]:
    rows = await session.scalars(
        select(Company)
        .where(Company.tenant_id == tenant_id)
        .order_by(Company.name)
        .limit(limit)
    )
    return [CompanyOut.model_validate(c) for c in rows]


@router.post("/companies", response_model=CompanyOut, status_code=201)
async def create_company(
    body: CompanyCreate, tenant_id: TenantId, session: DbSession
) -> CompanyOut:
    """Idempotente por nombre: volver a mandar la misma empresa devuelve la que
    ya existe en vez de fallar. Quien integra desde afuera no debería tener que
    consultar antes de crear."""
    key = _name_key(body.name)
    existing = await session.scalar(
        select(Company).where(Company.tenant_id == tenant_id, Company.name_key == key)
    )
    if existing is not None:
        return CompanyOut.model_validate(existing)

    company = Company(
        tenant_id=tenant_id,
        name=body.name.strip(),
        name_key=key,
        domain=body.domain,
        industry=body.industry,
        size=body.size,
    )
    session.add(company)
    await session.flush()
    log.info("company.created", company_id=str(company.id))
    return CompanyOut.model_validate(company)


# ── Oportunidades ───────────────────────────────────────────────────

@router.get("", response_model=list[DealOut])
async def list_deals(
    tenant_id: TenantId,
    session: DbSession,
    stage: str | None = Query(default=None),
    open_only: bool = Query(default=False),
    limit: int = Query(default=200, le=500),
) -> list[DealOut]:
    # Los nombres salen en el mismo query con outer joins: la tabla los muestra
    # en cada fila y resolverlos aparte sería un N+1 por carga de pantalla.
    stmt = (
        select(Deal, Contact.full_name, Company.name)
        .outerjoin(Contact, Contact.id == Deal.contact_id)
        .outerjoin(Company, Company.id == Deal.company_id)
        .where(Deal.tenant_id == tenant_id)
    )
    if stage:
        _check_stage(stage)
        stmt = stmt.where(Deal.stage == stage)
    if open_only:
        stmt = stmt.where(Deal.stage.in_(OPEN_STAGES))

    rows = await session.execute(stmt.order_by(Deal.created_at.desc()).limit(limit))
    out: list[DealOut] = []
    for deal, contact_name, company_name in rows.all():
        item = DealOut.model_validate(deal)
        item.contact_name = contact_name
        item.company_name = company_name
        out.append(item)
    return out


@router.post("", response_model=DealOut, status_code=201)
async def create_deal(
    body: DealCreate, tenant_id: TenantId, session: DbSession
) -> DealOut:
    _check_stage(body.stage)
    if body.contact_id is not None:
        contact = await session.get(Contact, body.contact_id)
        if contact is None or contact.tenant_id != tenant_id:
            raise NotFoundError("Contact not found")

    deal = Deal(
        tenant_id=tenant_id,
        contact_id=body.contact_id,
        company_id=body.company_id,
        title=body.title.strip(),
        stage=body.stage,
        amount_cents=body.amount_cents,
        currency=body.currency.upper(),
        expected_close_date=body.expected_close_date,
        owner=body.owner,
    )
    session.add(deal)
    await session.flush()
    log.info("deal.created", deal_id=str(deal.id), stage=deal.stage)
    return DealOut.model_validate(deal)


@router.patch("/{deal_id}", response_model=DealOut)
async def update_deal(
    deal_id: UUID, body: DealUpdate, tenant_id: TenantId, session: DbSession
) -> DealOut:
    deal = await session.get(Deal, deal_id)
    if deal is None or deal.tenant_id != tenant_id:
        raise NotFoundError("Deal not found")

    if body.stage is not None:
        _check_stage(body.stage)
        # `closed_at` lo pone el sistema, no el cliente: es la base del ciclo
        # de venta, y dejarlo editable convertiría esa métrica en una opinión.
        entering_closed = body.stage in CLOSED_STAGES and deal.stage not in CLOSED_STAGES
        leaving_closed = body.stage in OPEN_STAGES and deal.stage in CLOSED_STAGES
        if entering_closed:
            deal.closed_at = datetime.now(timezone.utc)
        elif leaving_closed:
            # Reabrir una oportunidad borra su cierre: si volviera a cerrarse,
            # el ciclo se mide desde el principio y no desde el cierre viejo.
            deal.closed_at = None
            deal.lost_reason = None
        deal.stage = body.stage

    for field in ("title", "amount_cents", "expected_close_date", "lost_reason", "owner", "company_id"):
        value = getattr(body, field)
        if value is not None:
            setattr(deal, field, value)

    await session.flush()
    log.info("deal.updated", deal_id=str(deal_id), stage=deal.stage)
    return DealOut.model_validate(deal)


@router.get("/pipeline", response_model=PipelineOut)
async def pipeline(tenant_id: TenantId, session: DbSession) -> PipelineOut:
    """El embudo en números: cuántas y cuánto por etapa.

    Una sola agregación en la base en vez de traer las filas y sumarlas en
    Python — con unos miles de oportunidades la diferencia deja de ser teórica.
    """
    rows = await session.execute(
        select(
            Deal.stage,
            func.count().label("n"),
            func.coalesce(func.sum(Deal.amount_cents), 0).label("total"),
            func.count(Deal.amount_cents).label("con_monto"),
        )
        .where(Deal.tenant_id == tenant_id)
        .group_by(Deal.stage)
    )
    por_etapa = {
        stage: (n, int(total), con_monto) for stage, n, total, con_monto in rows.all()
    }

    # Todas las etapas aparecen, incluso vacías: un embudo al que le faltan los
    # escalones sin datos no se lee como embudo.
    stages = [
        StageSummary(
            stage=s,
            count=por_etapa.get(s, (0, 0, 0))[0],
            amount_cents=por_etapa.get(s, (0, 0, 0))[1],
            with_amount=por_etapa.get(s, (0, 0, 0))[2],
        )
        for s in DEAL_STAGES
    ]

    abierto = sum(x.amount_cents for x in stages if x.stage in OPEN_STAGES)
    ganado = sum(x.amount_cents for x in stages if x.stage == "won")

    # Ciclo de venta promedio sobre las ganadas que tienen cierre registrado.
    dias = await session.scalar(
        select(
            func.avg(
                func.extract("epoch", Deal.closed_at - Deal.created_at) / 86400.0
            )
        ).where(
            Deal.tenant_id == tenant_id,
            Deal.stage == "won",
            Deal.closed_at.is_not(None),
        )
    )

    # La moneda del pipeline es la que más se usa. Mezclar monedas en un total
    # sería inventar un tipo de cambio; mostrar la dominante es honesto y
    # suficiente mientras un cliente opere en una sola.
    moneda = await session.scalar(
        select(Deal.currency)
        .where(Deal.tenant_id == tenant_id)
        .group_by(Deal.currency)
        .order_by(func.count().desc())
        .limit(1)
    )

    return PipelineOut(
        stages=stages,
        open_amount_cents=abierto,
        won_amount_cents=ganado,
        currency=moneda or "USD",
        avg_days_to_close=round(float(dias), 1) if dias is not None else None,
    )
