"""Banco de contenido: las piezas que el Content Agent generó y una persona guardó.

El agente PREPARA y una persona decide (P3), así que nada se publica solo: una
pieza nace `draft` y solo cambia de estado por una acción explícita.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, TenantId
from app.core.exceptions import NotFoundError
from app.models.content import ContentPiece

router = APIRouter()

FORMATS = {"reel", "carrusel", "historia", "post"}
PILLARS = {"autoridad", "conversion", "confianza", "atraccion"}
STATUSES = {"draft", "scheduled", "published"}


class PieceIn(BaseModel):
    format: str = Field(pattern="^(reel|carrusel|historia|post)$")
    pillar: str = Field(pattern="^(autoridad|conversion|confianza|atraccion)$")
    content: str = Field(min_length=1)
    context: str = ""
    zona: str = ""
    scheduled_for: datetime | None = None


class PieceUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(draft|scheduled|published)$")
    scheduled_for: datetime | None = None
    content: str | None = None


class PieceOut(BaseModel):
    id: UUID
    format: str
    pillar: str
    content: str
    context: str
    zona: str
    status: str
    scheduled_for: datetime | None
    created_at: datetime


def _out(p: ContentPiece) -> PieceOut:
    # `format` es palabra reservada de Python, así que en el modelo la columna se
    # llama `fmt` y se mapea acá. La API expone el nombre que usa la UI.
    return PieceOut(
        id=p.id,
        format=p.fmt,
        pillar=p.pillar,
        content=p.content,
        context=p.context,
        zona=p.zona,
        status=p.status,
        scheduled_for=p.scheduled_for,
        created_at=p.created_at,
    )


async def _get(session, tenant_id: UUID, piece_id: UUID) -> ContentPiece:
    piece = await session.get(ContentPiece, piece_id)
    if piece is None or piece.tenant_id != tenant_id:
        raise NotFoundError("Content piece not found")
    return piece


@router.get("", response_model=list[PieceOut])
async def list_pieces(
    tenant_id: TenantId,
    session: DbSession,
    piece_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, le=300),
) -> list[PieceOut]:
    stmt = select(ContentPiece).where(ContentPiece.tenant_id == tenant_id)
    if piece_status in STATUSES:
        stmt = stmt.where(ContentPiece.status == piece_status)
    stmt = stmt.order_by(ContentPiece.created_at.desc()).limit(limit)
    return [_out(p) for p in await session.scalars(stmt)]


@router.post("", response_model=PieceOut, status_code=status.HTTP_201_CREATED)
async def create_piece(body: PieceIn, tenant_id: TenantId, session: DbSession) -> PieceOut:
    piece = ContentPiece(
        tenant_id=tenant_id,
        fmt=body.format,
        pillar=body.pillar,
        content=body.content,
        context=body.context,
        zona=body.zona,
        scheduled_for=body.scheduled_for,
        status="scheduled" if body.scheduled_for else "draft",
    )
    session.add(piece)
    await session.flush()
    return _out(piece)


@router.patch("/{piece_id}", response_model=PieceOut)
async def update_piece(
    piece_id: UUID, body: PieceUpdate, tenant_id: TenantId, session: DbSession
) -> PieceOut:
    piece = await _get(session, tenant_id, piece_id)
    if body.content is not None:
        piece.content = body.content
    if body.scheduled_for is not None:
        piece.scheduled_for = body.scheduled_for
        piece.status = "scheduled"
    if body.status is not None:
        piece.status = body.status
    await session.flush()
    return _out(piece)


@router.delete("/{piece_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_piece(piece_id: UUID, tenant_id: TenantId, session: DbSession) -> None:
    piece = await _get(session, tenant_id, piece_id)
    await session.delete(piece)
