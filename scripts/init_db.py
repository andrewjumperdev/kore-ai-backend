"""Bootstrap local rápido (SOLO desarrollo).

Habilita pgvector y crea las tablas directo desde la metadata de SQLAlchemy,
salteando Alembic. Sirve para levantar un entorno local de cero en un segundo.

**En producción usá migraciones**: `alembic upgrade head` (o el rol `migrate`
del entrypoint de Docker). Con `create_all` no hay forma de evolucionar un
esquema que ya tiene datos: crea lo que falta, pero nunca altera ni renombra
una columna existente, así que el primer cambio de modelo te deja la base
silenciosamente desincronizada del código.

    python -m scripts.init_db
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine
from app.models import Base


async def main() -> None:
    if settings.is_production:
        print(
            "❌ init_db está deshabilitado en producción.\n"
            "   Usá: alembic upgrade head",
            file=sys.stderr,
        )
        raise SystemExit(1)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    print("✅ pgvector habilitado y tablas creadas (dev).")
    print("   Recordá stampear Alembic si vas a migrar después:")
    print("   alembic stamp head")


if __name__ == "__main__":
    asyncio.run(main())
