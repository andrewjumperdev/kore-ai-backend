"""Serie diaria de leads que alimenta la sparkline del dashboard.

El bug que se cuida acá es silencioso: un GROUP BY devuelve solo los días que
tuvieron leads. Si se grafica esa lista tal cual, el eje temporal se comprime y
la línea dibuja una tendencia que no ocurrió — cinco leads repartidos en dos
semanas se ven como cinco días seguidos de actividad.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from itertools import pairwise
from uuid import uuid4

import pytest

from app.orchestrator.metrics import MetricsService

AT = datetime(2026, 7, 27, 15, 0, tzinfo=timezone.utc)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeSession:
    """Devuelve las filas agrupadas que daría Postgres: solo días con datos."""

    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _stmt):
        return FakeResult(self.rows)


@pytest.fixture
def service():
    def _build(rows):
        return MetricsService(FakeSession(rows), uuid4())

    return _build


async def test_devuelve_exactamente_los_dias_pedidos(service):
    serie = await service([])._leads_daily(AT, days=14)
    assert len(serie) == 14


async def test_rellena_con_cero_los_dias_sin_leads(service):
    """Lo esencial: un día sin actividad es un cero, no una ausencia."""
    serie = await service([(date(2026, 7, 27), 3)])._leads_daily(AT, days=14)

    assert serie[-1] == {"date": "2026-07-27", "count": 3}
    assert all(d["count"] == 0 for d in serie[:-1])
    assert sum(d["count"] for d in serie) == 3


async def test_las_fechas_son_consecutivas_y_terminan_hoy(service):
    serie = await service([])._leads_daily(AT, days=14)

    fechas = [date.fromisoformat(d["date"]) for d in serie]
    assert fechas[-1] == AT.date()
    assert fechas[0] == AT.date() - timedelta(days=13)
    # pairwise dice lo que se quiere afirmar (cada par consecutivo) sin el
    # zip de largos distintos que obliga a discutir con `strict`.
    assert all(b - a == timedelta(days=1) for a, b in pairwise(fechas))


async def test_mapea_cada_conteo_a_su_dia(service):
    rows = [(date(2026, 7, 20), 2), (date(2026, 7, 25), 7)]
    serie = {d["date"]: d["count"] for d in await service(rows)._leads_daily(AT, days=14)}

    assert serie["2026-07-20"] == 2
    assert serie["2026-07-25"] == 7
    assert serie["2026-07-21"] == 0


async def test_ignora_dias_fuera_de_la_ventana(service):
    """Una fila anterior al inicio no debe colarse ni desplazar la serie."""
    rows = [(date(2026, 1, 1), 99), (date(2026, 7, 27), 1)]
    serie = await service(rows)._leads_daily(AT, days=14)

    assert len(serie) == 14
    assert sum(d["count"] for d in serie) == 1


async def test_acepta_fechas_como_texto(service):
    """Según el driver, func.date() puede volver como str en vez de date."""
    serie = {
        d["date"]: d["count"]
        for d in await service([("2026-07-26", 4)])._leads_daily(AT, days=14)
    }
    assert serie["2026-07-26"] == 4
