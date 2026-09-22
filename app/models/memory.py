from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


# Cómo se estableció un hecho, de más débil a más fuerte. El orden es lo que
# importa: un hecho deducido no puede pisar uno que la persona dijo con todas
# las letras. Sin este rango, el agente "corrige" con una inferencia lo que el
# cliente afirmó, y nadie se entera — que es exactamente la forma que tomó el
# bug del Coach pisando `business_profile`.
BASIS_RANK = {"inferred": 1, "imported": 2, "stated": 3, "operator": 4}
DEFAULT_BASIS = "inferred"


class LongTermMemory(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Durable, structured facts an agent should remember about a contact or
    the business (preferences, objections raised, key dates). Queried by key,
    not by similarity.

    Cada hecho viaja con su procedencia. Un valor sin saber de dónde salió no
    es un dato: es una afirmación anónima, y cuando resulta estar mal no hay
    forma de rastrear quién la hizo ni sobre qué base.
    """

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

    # ── Procedencia ────────────────────────────────────────────────────
    # `basis` es CÓMO se estableció (ver BASIS_RANK) y `source` es QUIÉN lo
    # produjo: el nombre del agente, "operator", "capture:web". Los dos son
    # necesarios: saber que algo fue deducido no dice quién lo dedujo.
    basis: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=DEFAULT_BASIS
    )
    source: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="unknown"
    )
    # La cita textual que sostiene el hecho. Es lo que permite mostrarle al
    # cliente POR QUÉ el sistema cree algo, en vez de pedirle que confíe.
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Cuándo ocurrió la observación, que no es cuándo se guardó: un mensaje de
    # ayer procesado hoy se observó ayer.
    observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


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
