from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import NicheStatus
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Niche(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A niche template — the heart of the replicable model.

    Andrew builds a niche ONCE; every client in that niche references it and
    inherits its calibrated configuration. A niche is platform-level (NOT
    tenant-scoped): it is shared across all tenants assigned to it.

    ``config`` carries everything that makes agents niche-aware (P2/P8):
      - coach_questions:      diagnostic questions for onboarding
      - qualification_signals: explicit signals → temperature
      - followup_sequences:   {cold|warm|hot: [steps...]}
      - proposal_template:    structure + positioning for the niche
      - content_templates:    posts/emails/scripts scaffolds
      - prompt_boundaries:    what the model may/may not assert (P8)
      - default_modules:      modules enabled by default after diagnosis
    """

    __tablename__ = "niches"

    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=NicheStatus.BUILDING, nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(default=99, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
