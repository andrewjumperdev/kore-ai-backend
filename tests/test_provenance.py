"""Procedencia de los hechos: quién lo dijo, cómo lo supo, y quién puede pisarlo.

La protección real vive en el `WHERE` del upsert, no en Python — dos corridas
concurrentes sobre el mismo contacto (webhook + scheduler) harían perder la
carrera a cualquier chequeo previo en memoria. Estos tests compilan la
sentencia y verifican que el guard está: si alguien lo saca en un refactor, un
hecho deducido vuelve a poder pisar lo que el cliente afirmó, en silencio.
"""
from __future__ import annotations

import uuid

from sqlalchemy.dialects import postgresql

from app.memory.long_term import LongTermMemoryStore
from app.models.memory import BASIS_RANK, DEFAULT_BASIS


class _CapturingSession:
    """Retiene la sentencia en vez de ejecutarla: alcanza para inspeccionar el
    SQL que se habría mandado."""

    def __init__(self) -> None:
        self.stmt = None

    async def execute(self, stmt):
        self.stmt = stmt
        return None


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


async def _remember(**kwargs) -> str:
    session = _CapturingSession()
    store = LongTermMemoryStore(session, uuid.uuid4())
    await store.remember("contact", "c-1", "presupuesto", {"monto": 100}, **kwargs)
    return _sql(session.stmt)


# ── El orden de las procedencias ────────────────────────────────────

def test_lo_que_la_persona_dijo_pesa_mas_que_lo_que_el_agente_dedujo():
    assert BASIS_RANK["stated"] > BASIS_RANK["inferred"]


def test_lo_que_carga_un_humano_pesa_mas_que_todo_lo_demas():
    """El operador es la última palabra: si alguien entró a corregir a mano, no
    hay agente que deba revertirlo."""
    assert BASIS_RANK["operator"] == max(BASIS_RANK.values())


def test_un_dato_importado_pesa_mas_que_una_inferencia_pero_menos_que_una_afirmacion():
    """Un lead que llegó por formulario trae datos que alguien tipeó: más
    confiable que una deducción, menos que lo que dijo en una conversación."""
    assert BASIS_RANK["inferred"] < BASIS_RANK["imported"] < BASIS_RANK["stated"]


# ── El guard en la escritura ────────────────────────────────────────

async def test_la_escritura_compara_procedencias_antes_de_pisar():
    """Sin este WHERE, el upsert sobrescribe siempre y toda la procedencia
    queda de adorno."""
    sql = await _remember(basis="inferred", source="sdr")
    assert "ON CONFLICT" in sql
    assert "WHERE" in sql.split("ON CONFLICT")[1]


async def test_el_guard_compara_por_rango_y_no_alfabeticamente():
    """`CASE` traduce el basis a su rango numérico. Comparar los strings daría
    'inferred' > 'imported' por orden alfabético, que es al revés de la
    realidad."""
    sql = await _remember(basis="stated", source="plaud")
    guard = sql.split("ON CONFLICT")[1]
    assert "CASE" in guard


async def test_la_procedencia_viaja_en_la_escritura():
    sql = await _remember(basis="stated", source="plaud", evidence="lo dijo en la reunión")
    for col in ("basis", "source", "evidence", "observed_at"):
        assert col in sql


# ── Defaults defensivos ─────────────────────────────────────────────

async def test_un_basis_inventado_cae_al_piso_en_vez_de_romper():
    """Un agente que devuelva basura no debe tumbar la escritura ni, peor,
    colarse con una procedencia alta que no existe."""
    session = _CapturingSession()
    store = LongTermMemoryStore(session, uuid.uuid4())
    await store.remember("contact", "c-1", "k", {"v": 1}, basis="altísima")
    params = session.stmt.compile(dialect=postgresql.dialect()).params
    assert params["basis"] == DEFAULT_BASIS


async def test_quien_no_declara_procedencia_no_puede_pisar_a_quien_si():
    """El default es el rango más bajo a propósito: omitir el dato no puede ser
    una forma de ganar la escritura."""
    assert BASIS_RANK[DEFAULT_BASIS] == min(BASIS_RANK.values())
