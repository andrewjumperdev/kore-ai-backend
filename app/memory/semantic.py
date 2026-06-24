"""Semantic memory backed by pgvector. Stores embedded text and retrieves the
nearest neighbors for retrieval-augmented agent reasoning."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.embeddings import embedder
from app.models.memory import SemanticMemory


class SemanticMemoryStore:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    async def index(
        self, kind: str, content: str, *, subject_id: str | None = None, meta: dict | None = None
    ) -> None:
        [vector] = await embedder.embed([content])
        self.session.add(
            SemanticMemory(
                tenant_id=self.tenant_id,
                kind=kind,
                subject_id=subject_id,
                content=content,
                embedding=vector,
                meta=meta or {},
            )
        )

    async def search(
        self, query: str, *, kind: str | None = None, limit: int = 5
    ) -> list[tuple[SemanticMemory, float]]:
        [qvec] = await embedder.embed([query])
        distance = SemanticMemory.embedding.cosine_distance(qvec)
        stmt = select(SemanticMemory, distance.label("distance")).where(
            SemanticMemory.tenant_id == self.tenant_id
        )
        if kind:
            stmt = stmt.where(SemanticMemory.kind == kind)
        stmt = stmt.order_by(distance).limit(limit)
        rows = await self.session.execute(stmt)
        return [(row[0], float(row[1])) for row in rows.all()]
