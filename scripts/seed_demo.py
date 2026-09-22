"""Puebla un tenant con contactos de prueba — SOLO DESARROLLO.

Sirve para ver el dashboard cargado sin esperar a que entren leads reales por
WhatsApp. Se niega a correr con KORE_ENV=production: estos contactos son
inventados y en la base de un cliente serían basura indistinguible de sus datos.

    python -m scripts.seed_demo              # el tenant más nuevo creado por la app
    python -m scripts.seed_demo t-c8799302   # uno puntual, por slug
    python -m scripts.seed_demo --limpiar    # borra lo que sembró
    python -m scripts.seed_demo --probar-procedencia   # verifica el guard de hechos

Sembrar es re-ejecutable: borra lo de la corrida anterior antes de sembrar de
nuevo, en la misma transacción.

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
from app.memory.long_term import LongTermMemoryStore
from app.models.contact import Contact
from app.models.crm import Deal
from app.models.memory import LongTermMemory
from app.models.conversation import Conversation, Message
from app.models.tenant import Tenant

MARCA = "demo"

# Oportunidades: (título, etapa, monto en centavos, días desde que se creó,
# días que tardó en cerrar o None si sigue abierta).
#
# Los montos y las etapas están elegidos para que el embudo de Analytics se vea
# como un embudo real —muchas arriba, pocas abajo— y para que haya al menos una
# ganada con cierre, que es lo único que hace que el ciclo de venta promedio
# devuelva un número en vez de "—".
NEGOCIOS = [
    ("Depto 2 amb. Gorriti",      "negotiation", 18_000_000, 22, None),
    ("Casa Nordelta",             "proposal",    32_000_000, 15, None),
    ("PH Belgrano",               "proposal",    21_000_000,  9, None),
    ("Depto Caballito",           "qualified",    9_500_000,  6, None),
    ("Loft Villa Crespo",         "qualified",   13_000_000,  4, None),
    ("Depto Almagro",             "new",           None,      2, None),  # sin monto aún
    ("Duplex Vicente López",      "new",         11_000_000,  1, None),
    ("Depto Palermo Soho",        "won",         16_500_000, 40, 12),
    ("Oficina Microcentro",       "won",         24_000_000, 55, 19),
    ("Depto Chacarita",           "lost",         7_800_000, 30, 21),
]

# Hechos con procedencia, para que la pestaña "Rastro" del contacto muestre la
# diferencia entre lo que la persona dijo y lo que el agente dedujo. Sin los
# tres tipos, no se ve que el sistema los distingue.
HECHOS = [
    ("presupuesto", {"maximo_usd": 180000}, "stated", "qualification",
     "Mi tope son 180 mil, no puedo estirarme más"),
    ("forma_de_pago", {"modo": "contado"}, "stated", "qualification",
     "Lo pago al contado, no necesito crédito"),
    ("urgencia", {"nivel": "alta", "razon": "vence alquiler"}, "inferred", "sdr",
     "Necesito mudarme antes de fin de mes"),
    ("zona_preferida", {"barrios": ["Palermo", "Villa Crespo"]}, "imported", "capture:web",
     None),
]

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

        # Re-ejecutable: borra lo sembrado antes de volver a sembrar. Sin esto,
        # la segunda corrida choca contra la restricción única del teléfono y
        # explota con un traceback de 200 líneas — para una herramienta de
        # desarrollo que uno corre varias veces por sesión, es inaceptable.
        # Va en la MISMA transacción que el sembrado: si algo falla a mitad,
        # el borrado se revierte y no te quedás sin los datos anteriores.
        previos, _, _ = await _borrar(session)
        if previos:
            print(f"♻️  {previos} contactos de una corrida anterior reemplazados.")

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

        # ── Oportunidades ───────────────────────────────────────────
        # Se cuelgan de los primeros contactos para que el detalle muestre algo
        # coherente: la persona que pregunta por Gorriti tiene esa oportunidad.
        primeros = await session.scalars(
            select(Contact)
            .where(Contact.tenant_id == tenant.id,
                   Contact.attributes[MARCA].astext == "true")
            .limit(len(NEGOCIOS))
        )
        contactos = list(primeros)

        for i, (titulo, etapa, monto, dias_edad, dias_cierre) in enumerate(NEGOCIOS):
            creado = ahora - timedelta(days=dias_edad)
            session.add(
                Deal(
                    tenant_id=tenant.id,
                    contact_id=contactos[i].id if i < len(contactos) else None,
                    title=titulo,
                    stage=etapa,
                    amount_cents=monto,
                    currency="USD",
                    created_at=creado,
                    # El cierre se calcula desde la creación, no desde hoy: es
                    # lo que hace que el ciclo de venta promedio dé el número
                    # que dicen los datos y no uno inventado por el seeder.
                    closed_at=(creado + timedelta(days=dias_cierre)) if dias_cierre else None,
                    lost_reason="Compró en otra inmobiliaria" if etapa == "lost" else None,
                    expected_close_date=(creado + timedelta(days=45)).date(),
                )
            )

        # ── Hechos con procedencia ──────────────────────────────────
        if contactos:
            store = LongTermMemoryStore(session, tenant.id)
            for key, value, basis, source, evidencia in HECHOS:
                await store.remember(
                    "contact", str(contactos[0].id), key, value,
                    basis=basis, source=source, evidence=evidencia,
                    observed_at=ahora - timedelta(hours=3),
                )

        print(f"✅ {len(CONTACTOS)} contactos, {len(NEGOCIOS)} oportunidades y "
              f"{len(HECHOS)} hechos en '{tenant.slug}'.")
        print("   Dashboard: tiles, tabla y pipeline con datos.")
        print("   Analytics: embudo, valor del pipeline y ciclo de venta.")
        print(f"   CRM > {contactos[0].full_name if contactos else 'un contacto'} > "
              "pestaña Rastro: los hechos con su procedencia.")


async def _borrar(session) -> tuple[int, int, int]:
    """Borra lo sembrado. Recibe la sesión en vez de abrir la suya para que
    `sembrar` pueda limpiar y volver a sembrar en una sola transacción: si el
    sembrado falla a mitad, el borrado se revierte con él."""
    rows = await session.scalars(
        select(Contact).where(Contact.attributes[MARCA].astext == "true")
    )
    contactos = list(rows)
    ids = [c.id for c in contactos]

    # Las oportunidades de esos contactos caen por el ON DELETE CASCADE del
    # FK, pero las que quedaron sin contacto (las últimas de la lista) no
    # tienen de quién colgar: se borran por título.
    n_deals = 0
    titulos = [t for t, *_ in NEGOCIOS]
    huerfanas = await session.scalars(select(Deal).where(Deal.title.in_(titulos)))
    for deal in huerfanas:
        await session.delete(deal)
        n_deals += 1

    # Los hechos no tienen FK al contacto (scope_id es texto), así que hay que
    # borrarlos a mano o quedan colgados apuntando a un contacto que ya no
    # existe.
    n_hechos = 0
    if ids:
        claves = [k for k, *_ in HECHOS]
        hechos = await session.scalars(
            select(LongTermMemory).where(
                LongTermMemory.scope == "contact",
                LongTermMemory.scope_id.in_([str(i) for i in ids]),
                LongTermMemory.key.in_(claves),
            )
        )
        for h in hechos:
            await session.delete(h)
            n_hechos += 1

    for contact in contactos:
        await session.delete(contact)
    await session.flush()
    return len(contactos), n_deals, n_hechos


async def limpiar() -> None:
    async with session_scope() as session:
        c, d, h = await _borrar(session)
        print(f"🧹 {c} contactos, {d} oportunidades y {h} hechos de prueba eliminados.")


async def probar_procedencia(slug: str | None) -> None:
    """Verifica contra la base real que un hecho débil no pisa a uno fuerte.

    Esta regla vive en el WHERE del upsert, así que los tests unitarios solo
    pueden comprobar que la sentencia se arma bien — no que Postgres la
    respete. Esto lo comprueba de verdad.
    """
    async with session_scope() as session:
        tenant = await _tenant(session, slug)
        if tenant is None:
            print("❌ No encontré un tenant.")
            raise SystemExit(1)

        store = LongTermMemoryStore(session, tenant.id)
        sujeto = "prueba-procedencia"
        ok = True

        async def leer() -> LongTermMemory | None:
            # `expire_all` es imprescindible: el upsert va por SQL crudo
            # (INSERT ... ON CONFLICT) y la sesión no se entera, así que el
            # identity map seguiría devolviendo la versión vieja de la fila y
            # la prueba mediría su propia caché en vez de lo que hizo Postgres.
            session.expire_all()
            filas = await store.recall_with_provenance("contact", sujeto)
            return filas[0] if filas else None

        # 1) La persona lo afirma.
        await store.remember("contact", sujeto, "presupuesto", {"usd": 180000},
                             basis="stated", source="qualification",
                             evidence="Mi tope son 180 mil")
        await session.flush()

        # 2) El agente "deduce" otra cosa. No debe ganar.
        await store.remember("contact", sujeto, "presupuesto", {"usd": 250000},
                             basis="inferred", source="sdr",
                             evidence="Parece que puede estirarse")
        await session.flush()

        f = await leer()
        if f and f.basis == "stated" and f.value.get("usd") == 180000:
            print("✅ Una inferencia NO pisó lo que la persona afirmó.")
        else:
            ok = False
            print(f"❌ El hecho quedó como {f.basis if f else '(vacío)'} "
                  f"= {f.value if f else None} — el guard no está funcionando.")

        # 3) Una persona del equipo lo corrige. Sí debe ganar.
        await store.remember("contact", sujeto, "presupuesto", {"usd": 195000},
                             basis="operator", source="operator",
                             evidence="Lo confirmé por teléfono")
        await session.flush()

        f = await leer()
        if f and f.basis == "operator" and f.value.get("usd") == 195000:
            print("✅ La corrección de una persona SÍ se impuso.")
        else:
            ok = False
            print(f"❌ El operador no pudo corregir: quedó {f.basis if f else '(vacío)'}.")

        # Limpieza: era un sujeto ficticio, no debe sobrevivir a la prueba.
        for fila in await store.recall_with_provenance("contact", sujeto):
            await session.delete(fila)

        if not ok:
            raise SystemExit(1)


def main() -> None:
    if settings.is_production:
        print("❌ seed_demo no corre en producción: son datos inventados.", file=sys.stderr)
        raise SystemExit(1)

    flags = {"--limpiar", "--probar-procedencia"}
    args = [a for a in sys.argv[1:] if a not in flags]
    slug = args[0] if args else None

    if "--limpiar" in sys.argv:
        asyncio.run(limpiar())
    elif "--probar-procedencia" in sys.argv:
        asyncio.run(probar_procedencia(slug))
    else:
        asyncio.run(sembrar(slug))


if __name__ == "__main__":
    main()
