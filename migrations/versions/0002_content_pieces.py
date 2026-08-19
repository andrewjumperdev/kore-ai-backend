"""content_pieces — banco de contenido persistente

Hasta acá el Content Agent generaba y la UI guardaba en memoria: al refrescar se
perdía todo. Esta tabla es el banco real.

Revision ID: 0002_content_pieces
Revises: 0001_baseline
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision = "0002_content_pieces"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_pieces",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False, index=True),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("pillar", sa.String(16), nullable=False),
        sa.Column("context", sa.Text(), nullable=False, server_default=""),
        sa.Column("zona", sa.String(120), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    # El listado siempre filtra por tenant y ordena por fecha; sin este índice
    # cada carga del banco recorre la tabla entera.
    op.create_index(
        "ix_content_pieces_tenant_created",
        "content_pieces",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_content_pieces_tenant_created", table_name="content_pieces")
    op.drop_table("content_pieces")
