"""Smoke test de seguridad contra un servidor EN VIVO.

Los tests de pytest verifican el código; esto verifica el *despliegue*: que la
instancia que está corriendo tiene los controles activos y con los secretos bien
puestos. Correlo después de cada deploy.

    # local (modo desarrollo: avisa de lo abierto en vez de fallar)
    python -m scripts.smoke_security

    # producción (exige que todo esté cerrado)
    python -m scripts.smoke_security --url https://api.tudominio.com --expect-prod

Sale con código 1 si algo que debería estar cerrado está abierto, así se puede
encadenar en un pipeline de deploy.
"""
from __future__ import annotations

import argparse
import sys

import httpx

TENANT = "00000000-0000-0000-0000-000000000000"

# La consola de Windows suele venir en cp1252, que no puede representar ✓/✗.
# Intentamos pasar stdout a UTF-8; si no se puede, degradamos a ASCII en vez de
# reventar con UnicodeEncodeError justo cuando el operador quiere leer el
# resultado de un deploy.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    OK, FAIL, WARN, ARROW = "\033[92m✓\033[0m", "\033[91m✗\033[0m", "\033[93m!\033[0m", "→"
except Exception:  # pragma: no cover - depende de la terminal
    OK, FAIL, WARN, ARROW = "[OK]", "[FALLA]", "[AVISO]", "->"


class Report:
    def __init__(self) -> None:
        self.failures = 0
        self.warnings = 0

    def check(self, name: str, passed: bool, detail: str = "") -> None:
        print(f"  {OK if passed else FAIL} {name}{f'  ({detail})' if detail else ''}")
        if not passed:
            self.failures += 1

    def warn(self, name: str, detail: str = "") -> None:
        print(f"  {WARN} {name}{f'  ({detail})' if detail else ''}")
        self.warnings += 1


def run(base: str, expect_prod: bool) -> int:
    base = base.rstrip("/")
    api = f"{base}/api/v1"
    rep = Report()

    with httpx.Client(timeout=15, follow_redirects=False) as c:
        # ── Disponibilidad ──────────────────────────────────────────
        print("\nDisponibilidad")
        try:
            health = c.get(f"{base}/health")
            rep.check("GET /health responde 200", health.status_code == 200)
        except httpx.HTTPError as exc:
            print(f"  {FAIL} no se pudo conectar a {base}: {exc}")
            return 1

        # Algunos controles (validar una API key) necesitan consultar la base.
        # Sin Postgres devuelven 500, que NO es un agujero de seguridad sino
        # infraestructura caída. Lo detectamos acá para no reportar una falla
        # falsa — un smoke test que miente es peor que no tenerlo.
        db_ok = False
        try:
            ready = c.get(f"{base}/health/ready")
            checks = ready.json().get("checks", {})
            db_ok = checks.get("postgres") == "ok"
            rep.check(
                "GET /health/ready: Postgres y Redis sanos",
                ready.status_code == 200,
                ", ".join(f"{k}={v}" for k, v in checks.items()),
            )
        except (httpx.HTTPError, ValueError):
            rep.warn("/health/ready no respondió JSON")

        # ── Alta de tenants ─────────────────────────────────────────
        print("\nAlta de tenants")
        resp = c.post(
            f"{api}/tenants",
            json={"name": "smoke", "slug": "smoke-test", "niche_slug": "real-estate"},
        )
        if expect_prod:
            rep.check(
                f"POST /tenants sin secreto {ARROW} 401",
                resp.status_code == 401,
                f"devolvió {resp.status_code}",
            )
        elif resp.status_code == 401:
            print(f"  {OK} POST /tenants pide secreto (ya cerrado en dev)")
        else:
            rep.warn("POST /tenants abierto", "normal en dev; en producción DEBE dar 401")

        # ── Webhooks ────────────────────────────────────────────────
        print("\nWebhooks")
        for provider in ("evolution", "plaud", "whatsapp"):
            resp = c.post(f"{api}/webhooks/{provider}/{TENANT}", json={"data": {}})
            closed = resp.status_code in (401, 503)
            if expect_prod:
                rep.check(
                    f"POST /webhooks/{provider} sin token {ARROW} 401/503",
                    closed,
                    f"devolvió {resp.status_code}",
                )
            elif closed:
                print(f"  {OK} /webhooks/{provider} exige token")
            else:
                rep.warn(f"/webhooks/{provider} acepta sin token", "normal en dev")

        # ── Datos de tenant (cerrados siempre, dev y prod) ───────────
        print("\nDatos de tenant (cerrados en dev y en prod)")
        for path in ("/contacts", "/metrics", "/escalations", "/billing/summary"):
            resp = c.get(f"{api}{path}")
            rep.check(
                f"GET {path} sin API key {ARROW} 401",
                resp.status_code == 401,
                f"devolvió {resp.status_code}",
            )

        if db_ok:
            resp = c.get(f"{api}/contacts", headers={"Authorization": "Bearer kore_inventada"})
            rep.check(
                f"GET /contacts con API key falsa {ARROW} 401",
                resp.status_code == 401,
                f"devolvió {resp.status_code}",
            )
        else:
            rep.warn(
                "API key falsa: no evaluable",
                "validar una key consulta la base, y Postgres no responde",
            )

        # ── Facturación ─────────────────────────────────────────────
        print("\nFacturación")
        resp = c.post(
            f"{api}/billing/admin/setup/paid",
            json={"tenant_id": TENANT},
            headers={"Authorization": "Bearer kore_key_de_un_cliente"},
        )
        rep.check(
            f"un tenant NO puede marcarse pagado {ARROW} 401",
            resp.status_code == 401,
            f"devolvió {resp.status_code}",
        )

        resp = c.post(f"{api}/billing/webhooks/stripe", json={"type": "invoice.paid"})
        rep.check(
            f"webhook de Stripe sin firma {ARROW} 401/503",
            resp.status_code in (401, 503),
            f"devolvió {resp.status_code}",
        )

        # ── Exposición ──────────────────────────────────────────────
        print("\nExposición")
        resp = c.get(f"{base}/docs")
        if expect_prod:
            rep.check(
                f"/docs apagado {ARROW} 404",
                resp.status_code == 404,
                f"devolvió {resp.status_code}",
            )
        else:
            print(f"  {OK} /docs disponible en dev (status {resp.status_code})")

    print()
    if rep.failures:
        print(f"{FAIL} {rep.failures} control(es) fallaron.")
        return 1
    if rep.warnings:
        print(f"{WARN} sin fallas; {rep.warnings} aviso(s) esperables en desarrollo.")
        return 0
    print(f"{OK} todos los controles pasaron.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000", help="base del servidor")
    parser.add_argument(
        "--expect-prod",
        action="store_true",
        help="exige el comportamiento de producción (todo cerrado)",
    )
    args = parser.parse_args()
    print(f"Smoke de seguridad {ARROW} {args.url}")
    sys.exit(run(args.url, args.expect_prod))
