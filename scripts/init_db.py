"""Fast local bootstrap (dev only) — enables pgvector and creates all tables
directly from the SQLAlchemy metadata, skipping Alembic. For production use
migrations (`alembic upgrade head`).

    python -m scripts.init_db
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.core.database import engine
from app.models import Base


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    print("✅ pgvector enabled and all tables created.")


if __name__ == "__main__":
    asyncio.run(main())
