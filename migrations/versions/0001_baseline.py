"""baseline — esquema completo derivado de los modelos

Punto de partida del historial de migraciones. Se genera desde
``Base.metadata`` en vez de DDL escrito a mano, a propósito:

* Los despliegues que ya existían se bootstrappearon con ``scripts/init_db.py``
  (``create_all``). Con ``checkfirst=True`` esta migración es un no-op sobre
  ellos y solo los deja *stampeados* en esta revisión — sin downtime ni riesgo
  de recrear tablas con datos.
* Sobre una base vacía crea exactamente el mismo esquema que ``init_db``.

**De acá en adelante las migraciones se escriben explícitas**, con
``alembic revision --autogenerate -m "…"``. Este archivo es el único que mira
los modelos en runtime; el resto congela el DDL, que es lo que permite revisar
un cambio de esquema en un diff.

Revision ID: 0001_baseline
Revises:
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.models import Base

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


# Las tablas que existían cuando se escribió esta baseline. La lista está FIJA a
# propósito: sin ella, `create_all` tomaría los modelos actuales y crearía
# también las tablas de migraciones posteriores — que después fallarían al
# intentar crearlas de nuevo, tumbando el upgrade entero en cualquier
# instalación desde cero. Una migración describe un momento, no el presente.
# No agregues nombres acá: cada tabla nueva va en su propia revisión.
BASELINE_TABLES = (
    "agent_runs",
    "contact_activities",
    "contacts",
    "conversations",
    "escalations",
    "events",
    "invoices",
    "leads",
    "long_term_memory",
    "messages",
    "niches",
    "prospects",
    "semantic_memory",
    "subscriptions",
    "tenant_api_keys",
    "tenant_integrations",
    "tenants",
    "users",
)


def _baseline_tables():
    return [Base.metadata.tables[name] for name in BASELINE_TABLES]


def upgrade() -> None:
    bind = op.get_bind()
    # pgvector: las columnas de memoria semántica dependen del tipo `vector`.
    bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=bind, tables=_baseline_tables(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=_baseline_tables())
