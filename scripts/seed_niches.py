"""Seed the launch niches from §03 (orden de construcción priorizado).

    python -m scripts.seed_niches

Each niche is the template Andrew builds ONCE; clients reference it and inherit
its calibrated configuration: preguntas del Coach (diagnóstico del onboarding),
señales de calificación 🔴🟡🟢, secuencias de follow-up, plantillas de contenido
y límites de prompt (P8).
"""
from __future__ import annotations

import asyncio

from app.core.database import session_scope
from app.core.enums import Module, NicheStatus
from app.services.niche_service import NicheService

ALL_MODULES = [m.value for m in Module]

NICHES = [
    {
        "slug": "plaud-ar",
        "name": "Plaud Argentina",
        "status": NicheStatus.ACTIVE,
        "priority": 1,
        "config": {
            "tone": "cercano, orientado a resultados",
            "coach_questions": [
                "¿Qué tipo de reuniones grabás con Plaud y con qué frecuencia?",
                "¿Cuál es tu ciclo de venta típico (días desde primer contacto a cierre)?",
                "¿Dónde se te escapan hoy los seguimientos?",
                "¿Cuántos prospectos nuevos manejás por semana?",
                "¿Qué canal usás más para hablar con clientes (WhatsApp, email, llamadas)?",
            ],
            "qualification_signals": {
                "hot": ["pide demo", "pregunta precio", "menciona urgencia"],
                "warm": ["pide info", "compara opciones"],
                "cold": ["solo curiosea", "sin presupuesto"],
            },
            "followup_sequences": {"hot": [1], "warm": [2, 5], "cold": [7, 21]},
            "content_templates": {
                "post": "Casos de uso de Plaud + KORE para captar y no perder seguimientos.",
                "email": "Secuencia de nurturing para usuarios Plaud que aún no escalan al sistema.",
            },
            "proposal_template": "Plaud como entrada + KORE como backend recurrente; conectar con el dolor de seguimiento.",
            "default_modules": ALL_MODULES,
            "prompt_boundaries": "Solo afirmar capacidades reales de Plaud + KORE. "
            "Nunca prometer autonomía 100% (P7).",
        },
    },
    {
        "slug": "constructoras",
        "name": "Constructoras / Desarrolladores",
        "status": NicheStatus.BUILDING,
        "priority": 2,
        "config": {
            "tone": "profesional, técnico, confiable",
            "coach_questions": [
                "¿Qué tipo de desarrollos manejás (residencial, comercial, lotes)?",
                "¿Cómo captás compradores/inversores hoy?",
                "¿Cuánto dura tu ciclo desde lead hasta reserva?",
                "¿Cuál es el ticket promedio de una unidad?",
                "¿Qué objeción escuchás más seguido y cómo la respondés hoy?",
            ],
            "qualification_signals": {
                "hot": ["pide cochera/unidad específica", "consulta financiación", "quiere visitar"],
                "warm": ["pide brochure", "consulta ubicación"],
                "cold": ["consulta general"],
            },
            "followup_sequences": {"hot": [1, 3], "warm": [3, 7], "cold": [14, 30]},
            "content_templates": {
                "post": "Avances de obra, render de unidades, ventajas de la zona y financiación.",
                "email": "Seguimiento de inversores con planes de pago y proyección de revalorización.",
            },
            "proposal_template": "Propuesta atada a la unidad/proyecto de interés + plan de financiación.",
            "default_modules": ALL_MODULES,
            "prompt_boundaries": "No prometer rentabilidades garantizadas ni fechas de entrega no confirmadas.",
        },
    },
    {
        "slug": "abogados",
        "name": "Abogados / Consultores",
        "status": NicheStatus.BUILDING,
        "priority": 3,
        "config": {
            "tone": "formal, confidencial",
            "coach_questions": [
                "¿Qué áreas del derecho/consultoría atendés?",
                "¿Cómo llegan hoy tus consultas (referidos, web, redes)?",
                "¿Qué tipo de caso es tu cliente ideal?",
                "¿Cuánto tarda en promedio de consulta inicial a contratación?",
                "¿Qué información necesitás SIEMPRE antes de tomar un caso?",
            ],
            "qualification_signals": {
                "hot": ["caso urgente", "pide reunión", "menciona plazos legales"],
                "warm": ["consulta concreta", "pide honorarios"],
                "cold": ["consulta general", "pregunta informativa"],
            },
            "followup_sequences": {"hot": [1], "warm": [2, 5], "cold": [10]},
            "content_templates": {
                "post": "Educación legal preventiva + autoridad en el área de práctica.",
                "email": "Seguimiento de consultas con próximos pasos claros (sin asesorar de fondo).",
            },
            "proposal_template": "Propuesta de honorarios atada al tipo de caso detectado en el diagnóstico.",
            "default_modules": ALL_MODULES,
            "prompt_boundaries": "Máxima confidencialidad. NO dar asesoramiento legal de fondo; "
            "solo captar y derivar. Escalar cualquier consulta sustantiva al humano.",
        },
    },
    {
        "slug": "real-estate",
        "name": "Real Estate / Inmobiliarias",
        "status": NicheStatus.BUILDING,
        "priority": 4,
        "config": {
            "tone": "cálido, ágil",
            "coach_questions": [
                "¿Operás venta, alquiler o ambos, y en qué zonas?",
                "¿Qué tipo de propiedades manejás principalmente?",
                "¿De dónde vienen tus leads hoy (portales, redes, referidos)?",
                "¿Trabajás solo/a o con un equipo? ¿Cuántas personas?",
                "¿Cuál es tu mayor cuello de botella: captar, responder o cerrar?",
            ],
            "qualification_signals": {
                "hot": ["quiere visitar", "pregunta precio", "tiene presupuesto definido", "menciona zona puntual"],
                "warm": ["pide info de una propiedad", "compara opciones"],
                "cold": ["consulta general", "sin presupuesto claro"],
            },
            "followup_sequences": {"hot": [1, 2], "warm": [3, 7], "cold": [14, 30]},
            "content_templates": {
                "post": "Propiedades destacadas, tips de compra/venta y novedades del mercado por zona.",
                "email": "Nurturing de compradores con propiedades que matchean su búsqueda.",
            },
            "proposal_template": "Propuesta atada a la propiedad/zona y operación (compra/venta/inversión) del lead.",
            "default_modules": ALL_MODULES,
            "prompt_boundaries": "No prometer precios ni disponibilidad sin confirmar. Escalar tasaciones al humano.",
        },
    },
    {
        "slug": "educacion",
        "name": "Educación / Instituciones",
        "status": NicheStatus.PLANNED,
        "priority": 5,
        "config": {
            "tone": "institucional, claro",
            "coach_questions": [
                "¿Qué programas/cursos ofrecés y a qué público?",
                "¿Cómo llegan hoy los interesados (web, ferias, redes)?",
                "¿Cuándo son tus períodos de inscripción?",
                "¿Cuál es el principal motivo por el que un interesado NO se inscribe?",
                "¿Qué datos necesitás de un interesado para hacer seguimiento?",
            ],
            "qualification_signals": {
                "hot": ["pregunta cómo inscribirse", "consulta fechas/precios", "pide entrevista"],
                "warm": ["pide plan de estudios", "compara programas"],
                "cold": ["consulta informativa"],
            },
            "followup_sequences": {"hot": [1], "warm": [3], "cold": [7, 21]},
            "content_templates": {
                "post": "Salida laboral, testimonios de egresados y fechas de inscripción.",
                "email": "Secuencia de nurturing hacia el cierre de inscripción.",
            },
            "proposal_template": "Propuesta de inscripción con beneficios y plan de pago según el programa de interés.",
            "default_modules": ALL_MODULES,
            "prompt_boundaries": "No prometer cupos ni becas no confirmadas.",
        },
    },
]


async def main() -> None:
    async with session_scope() as session:
        svc = NicheService(session)
        for n in NICHES:
            niche = await svc.upsert(**n)
            print(f"• niche: {niche.slug} ({niche.status}) prio={niche.priority}")
    print("✅ niches seeded.")


if __name__ == "__main__":
    asyncio.run(main())
