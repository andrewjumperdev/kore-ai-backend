"""Seed the launch niches from §03 (orden de construcción priorizado).

    python -m scripts.seed_niches

Each niche is the template Andrew builds ONCE; clients reference it and inherit
its calibrated configuration.
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
                "¿Qué tipo de reuniones grabás con Plaud?",
                "¿Cuál es tu ciclo de venta típico?",
                "¿Dónde se te escapan los seguimientos hoy?",
            ],
            "qualification_signals": {
                "hot": ["pide demo", "pregunta precio", "menciona urgencia"],
                "warm": ["pide info", "compara opciones"],
                "cold": ["solo curiosea", "sin presupuesto"],
            },
            "followup_sequences": {"hot": [1], "warm": [2, 5], "cold": [7, 21]},
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
                "¿Qué tipo de desarrollos manejás (residencial, comercial)?",
                "¿Cómo captás compradores/inversores hoy?",
                "¿Cuánto dura tu ciclo desde lead hasta reserva?",
            ],
            "qualification_signals": {
                "hot": ["pide cochera/unidad específica", "consulta financiación"],
                "warm": ["pide brochure", "consulta ubicación"],
                "cold": ["consulta general"],
            },
            "followup_sequences": {"hot": [1, 3], "warm": [3, 7], "cold": [14, 30]},
            "default_modules": ALL_MODULES,
        },
    },
    {
        "slug": "abogados",
        "name": "Abogados / Consultores",
        "status": NicheStatus.BUILDING,
        "priority": 3,
        "config": {
            "tone": "formal, confidencial",
            "prompt_boundaries": "Máxima confidencialidad. No dar asesoramiento "
            "legal; solo captar y derivar. Escalar cualquier consulta de fondo.",
            "followup_sequences": {"hot": [1], "warm": [2, 5], "cold": [10]},
            "default_modules": ALL_MODULES,
        },
    },
    {
        "slug": "real-estate",
        "name": "Real Estate / Inmobiliarias",
        "status": NicheStatus.BUILDING,
        "priority": 4,
        "config": {
            "tone": "cálido, ágil",
            "followup_sequences": {"hot": [1, 2], "warm": [3, 7], "cold": [14, 30]},
            "default_modules": ALL_MODULES,
        },
    },
    {
        "slug": "educacion",
        "name": "Educación / Instituciones",
        "status": NicheStatus.PLANNED,
        "priority": 5,
        "config": {
            "tone": "institucional, claro",
            "followup_sequences": {"hot": [1], "warm": [3], "cold": [7, 21]},
            "default_modules": ALL_MODULES,
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
