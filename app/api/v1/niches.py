from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.niche import Niche
from app.schemas.niche import NicheCreate, NicheOut
from app.services.niche_service import NicheService

router = APIRouter()


@router.get("", response_model=list[NicheOut])
async def list_niches(session: DbSession) -> list[NicheOut]:
    """The niche catalog Andrew builds once each (§03)."""
    rows = await session.scalars(select(Niche).order_by(Niche.priority))
    return [NicheOut.model_validate(n) for n in rows]


@router.post("", response_model=NicheOut, status_code=status.HTTP_201_CREATED)
async def upsert_niche(body: NicheCreate, session: DbSession) -> NicheOut:
    niche = await NicheService(session).upsert(
        slug=body.slug,
        name=body.name,
        status=body.status,
        priority=body.priority,
        config=body.config,
    )
    return NicheOut.model_validate(niche)
