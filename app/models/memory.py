from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class LongTermMemory(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Durable, structured facts an agent should remember about a contact or
    the business (preferences, objections raised, key dates). Queried by key,
    not by similarity."""

    __tablename__ = "long_term_memory"
    __table_args__ = (
        Index("ix_ltm_scope", "tenant_id", "scope", "scope_id", "key"),
        UniqueConstraint(
            "tenant_id", "scope", "scope_id", "key", name="uq_ltm_scope_key"
        ),
    )

    scope: Mapped[str] = mapped_column(String(32), nullable=False)  # contact | business | agent
    # "global" sentinel when not bound to a specific entity, so the unique
    # constraint dedups (Postgres treats NULLs as distinct).
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False, default="global")
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class SemanticMemory(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Embedded text chunks for retrieval-augmented agent reasoning
    (past conversations, knowledge base, won/lost notes)."""

    __tablename__ = "semantic_memory"
    __table_args__ = (
        # IVFFlat/HNSW index is created in a migration (needs data/extension).
        Index("ix_semmem_tenant_kind", "tenant_id", "kind"),
    )

    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # conversation | kb | note
    subject_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embed_dim), nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
