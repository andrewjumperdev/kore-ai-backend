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


def upgrade() -> None:
    bind = op.get_bind()
    # pgvector: las columnas de memoria semántica dependen del tipo `vector`.
    bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
