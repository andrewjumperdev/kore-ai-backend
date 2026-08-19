"""Puebla un tenant con contactos de prueba — SOLO DESARROLLO.

Sirve para ver el dashboard cargado sin esperar a que entren leads reales por
WhatsApp. Se niega a correr con KORE_ENV=production: estos contactos son
inventados y en la base de un cliente serían basura indistinguible de sus datos.

    python -m scripts.seed_demo              # el tenant más nuevo creado por la app
    python -m scripts.seed_demo t-c8799302   # uno puntual, por slug
    python -m scripts.seed_demo --limpiar    # borra lo que sembró

Todo lo que crea lleva `demo: true` en `attributes`, así el borrado es exacto y
nunca toca un contacto real.
"""
from __future__ import annotations

import asyncio
import sys

# La consola de Windows viene en cp1252 y no puede imprimir ✅/🧹. Sin esto el
# script falla en el print final DESPUÉS de haber hecho el trabajo, y como el
# print está dentro del `session_scope`, la excepción revierte todo.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover - depende de la terminal
    pass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.database import session_scope
from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.models.tenant import Tenant

MARCA = "demo"

# Minutos de espera + el último mensaje entrante. Los tiempos están elegidos para
# que se vean los tres estados del dashboard: recién llegado, esperando, y
# caliente pasado de las 2 h que dispara la alerta.
CONTACTOS = [
    ("Sofía Ramírez",  "+5491133334441", "hot",   4,    "Palermo · USD 180k",      "¿Sigue disponible el 2 ambientes de Gorriti?"),
    ("Martín Duarte",  "+5491133334442", "hot",   12,   "Nordelta · USD 320k",     "Quiero coordinar una visita el sábado"),
    ("Valeria Sosa",   "+5491133334443", "hot",   190,  "Belgrano · USD 210k",     "¿Aceptan permuta por un depto más chico?"),
    ("Lucía Benítez",  "+5491133334444", "warm",  38,   "Caballito · USD 95k",     "¿Cuánto son las expensas?"),
    ("Andrés Ferreyra","+5491133334445", "warm",  75,   "Vicente López · s/d",     "Estoy viendo opciones todavía"),
    ("Nicolás Pérez",  "+5491133334446", "warm",  300,  "Villa Crespo · USD 130k", "Me interesa pero necesito crédito"),
    ("Camila Ortiz",   "+5491133334447", "cold",  600,  "Belgrano · USD 140k",     "Gracias, lo pienso y te aviso"),
    ("Hernán Vidal",   "+5491133334448", "cold",  1500, "Almagro · s/d",           "Por ahora solo estoy mirando"),
    ("Paula Giménez",  "+5491133334449", "unset", 25,   "",                        "Hola, vi el aviso de Chacarita"),
]


async def _tenant(session, slug: str | None) -> Tenant | None:
    stmt = select(Tenant)
    stmt = (
        stmt.where(Tenant.slug == slug)
        if slug
        else stmt.where(Tenant.slug.like("t-%")).order_by(Tenant.created_at.desc())
    )
    return await session.scalar(stmt.limit(1))


async def sembrar(slug: str | None) -> None:
    async with session_scope() as session:
        tenant = await _tenant(session, slug)
        if tenant is None:
            print(
                "❌ No encontré un tenant.\n"
                "   Entrá a la app, completá el onboarding y volvé a correr esto."
            )
            raise SystemExit(1)

        ahora = datetime.now(timezone.utc)
        for nombre, tel, temp, minutos, datos, mensaje in CONTACTOS:
            visto = ahora - timedelta(minutes=minutos)
            contact = Contact(
                tenant_id=tenant.id,
                identity_key=tel,
                full_name=nombre,
                phone=tel,
                temperature=temp,
                lifecycle_stage="qualified" if temp in ("hot", "warm") else "lead",
                last_activity_at=visto,
                attributes={MARCA: "true", **({"zona": datos} if datos else {})},
            )
            session.add(contact)
            await session.flush()

            conv = Conversation(
                tenant_id=tenant.id, contact_id=contact.id, channel="evolution"
            )
            session.add(conv)
            await session.flush()
            session.add(
                Message(
                    tenant_id=tenant.id,
                    conversation_id=conv.id,
                    direction="inbound",
                    role="user",
                    body=mensaje,
                    created_at=visto,
                )
            )

        print(f"✅ {len(CONTACTOS)} contactos de prueba en '{tenant.slug}'.")
        print("   Abrí el dashboard: los tiles, la tabla y el pipeline ya tienen datos.")


async def limpiar() -> None:
    async with session_scope() as session:
        rows = await session.scalars(
            select(Contact).where(Contact.attributes[MARCA].astext == "true")
        )
        n = 0
        for contact in rows:
            await session.delete(contact)
            n += 1
        print(f"🧹 {n} contactos de prueba eliminados.")


def main() -> None:
    if settings.is_production:
        print("❌ seed_demo no corre en producción: son datos inventados.", file=sys.stderr)
        raise SystemExit(1)

    args = [a for a in sys.argv[1:] if a != "--limpiar"]
    if "--limpiar" in sys.argv:
        asyncio.run(limpiar())
    else:
        asyncio.run(sembrar(args[0] if args else None))


if __name__ == "__main__":
    main()
