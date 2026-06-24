"""End-to-end demonstration of the KORE IA chain, run inline (no worker) so the
whole pipeline is visible in one process.

    python -m scripts.init_db
    python -m scripts.seed_niches
    python -m scripts.demo_flow

Uses the LLM stub unless ANTHROPIC_API_KEY is set, so it runs fully offline.
Shows: niche → client (Coach diagnosis enables modules) → lead intake (SDR, no
outbound, P1) → Qualification (temperature) → Follow-up / Proposal (escalates to
human, P3) → billing (setup + MRR) → metrics + escalations.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import select

from app.agents.runner import AgentRunner
from app.core.context import tenant_context
from app.core.database import session_scope
from app.models.contact import Contact
from app.models.escalation import Escalation
from app.models.tenant import Tenant
from app.orchestrator.metrics import MetricsService
from app.services.lead_service import LeadService
from app.services.niche_service import NicheService


async def main() -> None:
    async with session_scope() as session:
        # ── 0. Niche must exist (run scripts.seed_niches first) ──────
        niche = await NicheService(session).by_slug("constructoras")
        if niche is None:
            print("⚠  Run `python -m scripts.seed_niches` first.")
            return

        # ── 1. Provision a client as an instance of the niche (P2) ───
        tenant = Tenant(
            name="Beltrán Briones Desarrollos",
            slug=f"bb-{datetime.now():%H%M%S}",
            niche_id=niche.id,
        )
        session.add(tenant)
        await session.flush()
        tid = tenant.id
        print(f"• cliente creado en nicho '{niche.slug}': {tenant.slug}")

    with tenant_context(tid):
        # ── 2. Coach diagnoses + enables modules ─────────────────────
        async with session_scope() as session:
            await AgentRunner(session, tid).run(
                "coach",
                {"message": "Desarrollo edificios residenciales premium. Capto "
                 "inversores por Instagram y referidos. Ciclo ~3 meses."},
            )
        async with session_scope() as session:
            t = await session.get(Tenant, tid)
            print(f"• coach: diagnóstico ok, módulos habilitados = {t.enabled_modules}")

        # ── 3. Billing: setup + MRR, then mark setup paid (deal) ─────
        async with session_scope() as session:
            from app.billing.engine import BillingEngine

            engine = BillingEngine(session)
            await engine.create_subscription(
                tid, plan="constructoras-growth", setup_fee_cents=150000, mrr_cents=49900
            )
            summary = await engine.mark_setup_paid(tid)
            print(f"• billing: setup pagado, MRR ${summary['mrr_cents']/100:.2f}, "
                  f"estado={summary['status']} → deal.closed dispara Onboarding")

        # ── 4. New lead → SDR intake (NO outbound, P1) ───────────────
        async with session_scope() as session:
            lead = await LeadService(session, tid).create_lead(
                full_name="Inversor Lead", phone="+5491133334444",
                channel="whatsapp", source="instagram",
            )
            print(f"• lead creado: {lead.id} (emite lead.created → SDR)")

        async with session_scope() as session:
            contact = await session.scalar(
                select(Contact).where(Contact.tenant_id == tid).order_by(Contact.created_at.desc())
            )
            sdr = await AgentRunner(session, tid).run(
                "sdr",
                {"contact_id": str(contact.id), "channel": "whatsapp", "to": contact.phone},
            )
            print(f"• sdr: temperatura inicial = {sdr.output['temperature']} "
                  f"(sin mensaje saliente — P1)")

        # ── 5. Qualification sets the definitive temperature ─────────
        async with session_scope() as session:
            qual = await AgentRunner(session, tid).run(
                "qualification",
                {"contact_id": str(contact.id), "channel": "whatsapp",
                 "to": contact.phone, "message": "Me interesa, ¿qué unidades tienen?"},
            )
            print(f"• qualification: temperatura = {qual.output['temperature']}")

        # ── 6. Proposal prepares + escalates to human (P3/P6) ────────
        async with session_scope() as session:
            await AgentRunner(session, tid).run(
                "proposal",
                {"contact_id": str(contact.id), "channel": "whatsapp", "to": contact.phone},
            )

        # ── 7. Escalations (human queue) + metrics snapshot ──────────
        async with session_scope() as session:
            escs = (await session.scalars(
                select(Escalation).where(Escalation.tenant_id == tid)
            )).all()
            print(f"• escalaciones a humano: {[e.reason for e in escs]}")
            snap = await MetricsService(session, tid).snapshot()
            print(f"• métricas: temp={snap['temperature_distribution']} "
                  f"clasificación={snap['auto_classification_rate']} "
                  f"MRR=${snap['mrr_cents']/100:.2f} alerts={len(snap['alerts'])}")

    print("\n✅ demo flow KORE IA completo.")


if __name__ == "__main__":
    asyncio.run(main())
