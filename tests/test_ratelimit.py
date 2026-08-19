"""Rate limiting y cuota mensual de tokens — los frenos de gasto de la API."""
from __future__ import annotations

import pytest
from starlette.requests import Request

from app.billing import quota
from app.core import ratelimit
from app.core.exceptions import QuotaExceeded, RateLimitExceeded


class FakeRedis:
    """Redis en memoria con lo justo: INCR/EXPIRE/GET/INCRBY vía pipeline."""

    def __init__(self, *, broken: bool = False):
        self.store: dict[str, int] = {}
        self.broken = broken

    def pipeline(self):
        return FakePipeline(self)

    async def get(self, key):
        if self.broken:
            raise ConnectionError("redis caído")
        return self.store.get(key)


class FakePipeline:
    def __init__(self, redis: FakeRedis):
        self.redis = redis
        self.ops: list = []

    def incr(self, key):
        self.ops.append(("incr", key, 1))

    def incrby(self, key, amount):
        self.ops.append(("incr", key, amount))

    def expire(self, key, ttl):
        self.ops.append(("expire", key, ttl))

    async def execute(self):
        if self.redis.broken:
            raise ConnectionError("redis caído")
        results = []
        for op, key, arg in self.ops:
            if op == "incr":
                self.redis.store[key] = self.redis.store.get(key, 0) + arg
                results.append(self.redis.store[key])
            else:
                results.append(True)
        return results


@pytest.fixture
def redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(ratelimit, "redis_client", fake)
    monkeypatch.setattr(quota, "redis_client", fake)
    return fake


@pytest.fixture
def limits_on(monkeypatch, make_settings):
    monkeypatch.setattr(ratelimit, "settings", make_settings(rate_limit_enabled=True))


# ── Rate limit ──────────────────────────────────────────────────────

async def test_deja_pasar_hasta_el_limite(redis, limits_on):
    for _ in range(3):
        await ratelimit.hit("test", limit=3)


async def test_corta_al_pasarse(redis, limits_on):
    for _ in range(3):
        await ratelimit.hit("test", limit=3)
    with pytest.raises(RateLimitExceeded) as exc:
        await ratelimit.hit("test", limit=3)
    assert 0 < exc.value.retry_after <= 60
    assert exc.value.status_code == 429


async def test_los_buckets_son_independientes(redis, limits_on):
    """Un tenant abusivo no debe afectar a los demás."""
    await ratelimit.hit("tenant-a", limit=1)
    await ratelimit.hit("tenant-b", limit=1)  # no hereda el consumo de A
    with pytest.raises(RateLimitExceeded):
        await ratelimit.hit("tenant-a", limit=1)


async def test_redis_caido_deja_pasar(monkeypatch, limits_on):
    """Fail-open: un incidente de Redis no puede voltear toda la API."""
    monkeypatch.setattr(ratelimit, "redis_client", FakeRedis(broken=True))
    for _ in range(50):
        await ratelimit.hit("test", limit=1)


async def test_desactivado_no_cuenta(redis, monkeypatch, make_settings):
    monkeypatch.setattr(ratelimit, "settings", make_settings(rate_limit_enabled=False))
    for _ in range(50):
        await ratelimit.hit("test", limit=1)


async def test_limite_cero_no_bloquea(redis, limits_on):
    """limit<=0 significa "sin límite", no "bloquear todo"."""
    for _ in range(10):
        await ratelimit.hit("test", limit=0)


# ── IP del cliente detrás del proxy ─────────────────────────────────

def _request(headers: dict | None = None, client=("10.0.0.1", 1)) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
            "client": client,
        }
    )


def test_usa_el_peer_directo_sin_proxy():
    assert ratelimit.client_ip(_request()) == "10.0.0.1"


def test_toma_la_ip_de_mas_a_la_derecha_del_xff():
    """Caddy appendea su peer real: la primera entrada la escribe el cliente y
    tomarla permitiría evadir el límite rotando un XFF inventado."""
    req = _request({"x-forwarded-for": "1.1.1.1, 203.0.113.9"})
    assert ratelimit.client_ip(req) == "203.0.113.9"


# ── Cuota mensual de tokens ─────────────────────────────────────────

@pytest.fixture
def quota_on(monkeypatch, make_settings):
    monkeypatch.setattr(quota, "settings", make_settings(token_quota_monthly=1000))


async def test_cuota_permite_bajo_el_techo(redis, quota_on):
    await quota.record("tenant-1", 900)
    await quota.check("tenant-1")


async def test_cuota_corta_al_llegar_al_techo(redis, quota_on):
    await quota.record("tenant-1", 1000)
    with pytest.raises(QuotaExceeded) as exc:
        await quota.check("tenant-1")
    assert exc.value.status_code == 402


async def test_la_cuota_es_por_tenant(redis, quota_on):
    await quota.record("tenant-1", 5000)
    await quota.check("tenant-2")  # otro tenant no se ve afectado


async def test_sin_cuota_configurada_no_limita(redis, monkeypatch, make_settings):
    monkeypatch.setattr(quota, "settings", make_settings(token_quota_monthly=0))
    await quota.record("tenant-1", 10_000_000)
    await quota.check("tenant-1")


async def test_cuota_con_redis_caido_no_rompe_el_flujo(monkeypatch, quota_on):
    monkeypatch.setattr(quota, "redis_client", FakeRedis(broken=True))
    await quota.record("tenant-1", 500)   # no propaga
    await quota.check("tenant-1")         # sin datos → deja pasar
