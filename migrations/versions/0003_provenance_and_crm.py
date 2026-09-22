"""Procedencia en los hechos + empresas y oportunidades.

Tres cambios que van juntos porque comparten el mismo objetivo: que el CRM
pueda responder de dónde salió cada dato y cuánto vale cada oportunidad.

1. `long_term_memory` gana basis/source/evidence/observed_at. Las filas que ya
   existen se marcan como `inferred` desde una fuente desconocida — que es
   exactamente lo que son: las escribió un agente sin dejar rastro.
2. `companies` y `deals`, las entidades que faltaban para medir el pipeline.
3. `contacts.company_id`, para colgar la persona de su organización.

Revision ID: 0003_provenance_and_crm
Revises: 0002_content_pieces
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID

revision = "0003_provenance_and_crm"
down_revision = "0002_content_pieces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1) Procedencia ──────────────────────────────────────────────────
    # server_default en las dos columnas NOT NULL: sin eso, ALTER sobre una
    # tabla con filas falla. Se deja puesto (no se saca después) porque una
    # escritura que no declara procedencia debe caer al piso, no romper.
    op.add_column(
        "long_term_memory",
        sa.Column("basis", sa.String(16), nullable=False, server_default="inferred"),
    )
    op.add_column(
        "long_term_memory",
        sa.Column("source", sa.String(64), nullable=False, server_default="unknown"),
    )
    op.add_column("long_term_memory", sa.Column("evidence", sa.Text(), nullable=True))
    op.add_column(
        "long_term_memory",
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── 2) Empresas ─────────────────────────────────────────────────────
    op.create_table(
        "companies",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_key", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(255), nullable=True),
        sa.Column("industry", sa.String(120), nullable=True),
        sa.Column("size", sa.String(32), nullable=True),
        sa.Column("attributes", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("tenant_id", "name_key", name="uq_company_name"),
    )
    op.create_index("ix_company_domain", "companies", ["tenant_id", "domain"])

    # ── 3) Oportunidades ────────────────────────────────────────────────
    op.create_table(
        "deals",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "contact_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "company_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False, server_default="new"),
        # BigInteger: en pesos argentinos un depto de USD 200k son ~2.6e8
        # centavos, todavía lejos del techo, pero Integer quedaría justo.
        sa.Column("amount_cents", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lost_reason", sa.Text(), nullable=True),
        sa.Column("owner", sa.String(120), nullable=True),
        sa.Column("attributes", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_deal_stage", "deals", ["tenant_id", "stage"])
    op.create_index("ix_deal_contact", "deals", ["tenant_id", "contact_id"])

    # ── 4) El contacto cuelga de su empresa ─────────────────────────────
    op.add_column(
        "contacts",
        sa.Column(
            "company_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("contacts", "company_id")
    op.drop_index("ix_deal_contact", table_name="deals")
    op.drop_index("ix_deal_stage", table_name="deals")
    op.drop_table("deals")
    op.drop_index("ix_company_domain", table_name="companies")
    op.drop_table("companies")
    for col in ("observed_at", "evidence", "source", "basis"):
        op.drop_column("long_term_memory", col)
