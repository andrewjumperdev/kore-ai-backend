"""Long-term memory in Postgres — durable structured facts (key/value JSON),
queried by scope + key rather than similarity. Writes are idempotent upserts on
(tenant_id, scope, scope_id, key).

Cada escritura lleva su procedencia y **compite** con lo que ya había: un hecho
deducido no pisa uno que la persona afirmó. La comparación se hace en el propio
UPDATE, no en Python, porque dos corridas del agente sobre el mismo contacto
pueden ser concurrentes (webhook + tarea del scheduler) y un read-then-write
perdería la carrera en silencio.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import BASIS_RANK, DEFAULT_BASIS, LongTermMemory

_GLOBAL = "global"


def _rank(column):
    """El rango de un `basis` como expresión SQL. Un valor desconocido cae al
    piso: ante la duda, no pisa nada."""
    return case(BASIS_RANK, value=column, else_=0)


class LongTermMemoryStore:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    async def remember(
        self,
        scope: str,
        scope_id: str | None,
        key: str,
        value: dict,
        *,
        basis: str = DEFAULT_BASIS,
        source: str = "unknown",
        evidence: str | None = None,
        observed_at: datetime | None = None,
    ) -> None:
        """Graba un hecho si su procedencia es al menos tan fuerte como la del
        que ya estaba.

        El default es `inferred` a propósito: quien no declara cómo lo supo,
        no puede sobrescribir a quien sí lo declaró.
        """
        sid = scope_id or _GLOBAL
        if basis not in BASIS_RANK:
            basis = DEFAULT_BASIS

        stmt = insert(LongTermMemory).values(
            tenant_id=self.tenant_id,
            scope=scope,
            scope_id=sid,
            key=key,
            value=value,
            basis=basis,
            source=source,
            evidence=evidence,
            observed_at=observed_at,
        )
        # `where` sobre el DO UPDATE: si el hecho existente tiene mejor
        # procedencia, el upsert no hace nada y no falla. Es deliberado que sea
        # `>=` y no `>`: una observación nueva de la misma fuerza es más
        # reciente, y debe ganar.
        stmt = stmt.on_conflict_do_update(
            constraint="uq_ltm_scope_key",
            set_={
                "value": stmt.excluded.value,
                "basis": stmt.excluded.basis,
                "source": stmt.excluded.source,
                "evidence": stmt.excluded.evidence,
                "observed_at": stmt.excluded.observed_at,
            },
            where=_rank(stmt.excluded.basis) >= _rank(LongTermMemory.basis),
        )
        await self.session.execute(stmt)

    async def recall(self, scope: str, scope_id: str | None) -> dict[str, dict]:
        """Solo los valores — es lo que el agente necesita en su contexto, y
        cargarle la procedencia sería ruido que se lleva tokens."""
        rows = await self.session.scalars(
            select(LongTermMemory).where(
                LongTermMemory.tenant_id == self.tenant_id,
                LongTermMemory.scope == scope,
                LongTermMemory.scope_id == (scope_id or _GLOBAL),
            )
        )
        return {row.key: row.value for row in rows}

    async def recall_with_provenance(
        self, scope: str, scope_id: str | None
    ) -> list[LongTermMemory]:
        """Los hechos con su respaldo, para mostrarle al cliente en qué se basa
        el sistema. Devuelve filas, no un dict: la UI necesita los metadatos."""
        rows = await self.session.scalars(
            select(LongTermMemory)
            .where(
                LongTermMemory.tenant_id == self.tenant_id,
                LongTermMemory.scope == scope,
                LongTermMemory.scope_id == (scope_id or _GLOBAL),
            )
            .order_by(LongTermMemory.key)
        )
        return list(rows)
