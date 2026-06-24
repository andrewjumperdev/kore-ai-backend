"""Metrics the Orchestrator measures (§08). Tenant-scoped, computed from the
durable models/events (P5 — the database is the system's memory). Each metric
carries its threshold so the orchestrator can raise alerts deterministically.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EscalationStatus, Temperature
from app.models.billing import Subscription
from app.models.contact import Contact
from app.models.escalation import Escalation
from app.models.lead import Lead


class MetricsService:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    async def snapshot(self, at: datetime | None = None) -> dict:
        at = at or datetime.now(timezone.utc)
        week_ago = at - timedelta(days=7)

        leads_7d = await self._count(
            select(func.count(Lead.id)).where(
                Lead.tenant_id == self.tenant_id, Lead.created_at >= week_ago
            )
        )
        temp_dist = await self._temperature_distribution()
        total_contacts = sum(temp_dist.values()) or 1
        classified = total_contacts - temp_dist.get(Temperature.UNSET, 0)
        plaud_leads = await self._count(
            select(func.count(Lead.id)).where(
                Lead.tenant_id == self.tenant_id, Lead.source == "plaud"
            )
        )
        open_escalations = await self._count(
            select(func.count(Escalation.id)).where(
                Escalation.tenant_id == self.tenant_id,
                Escalation.status == EscalationStatus.OPEN,
            )
        )
        sub = await self.session.scalar(
            select(Subscription).where(Subscription.tenant_id == self.tenant_id)
        )

        cold_share = temp_dist.get(Temperature.COLD, 0) / total_contacts
        snapshot = {
            "leads_new_7d": leads_7d,
            "temperature_distribution": {k: v for k, v in temp_dist.items()},
            "auto_classification_rate": round(classified / total_contacts, 3),
            "cold_share": round(cold_share, 3),
            "plaud_leads": plaud_leads,
            "open_escalations": open_escalations,
            "mrr_cents": sub.mrr_cents if sub and sub.status == "active" else 0,
            "subscription_status": sub.status if sub else "none",
        }
        snapshot["alerts"] = self._evaluate_alerts(snapshot)
        return snapshot

    def _evaluate_alerts(self, s: dict) -> list[dict]:
        alerts = []
        if s["leads_new_7d"] < 5:
            alerts.append({"metric": "leads_new_7d", "issue": "captación baja",
                           "action": "revisar fuente de leads"})
        if s["auto_classification_rate"] < 0.80:
            alerts.append({"metric": "auto_classification_rate",
                           "issue": "< 80% clasificado", "action": "revisar prompts Qualification"})
        if s["cold_share"] > 0.60:
            alerts.append({"metric": "cold_share", "issue": "> 60% frío",
                           "action": "revisar fuente de captación"})
        return alerts

    async def _temperature_distribution(self) -> dict[str, int]:
        rows = await self.session.execute(
            select(Contact.temperature, func.count(Contact.id))
            .where(Contact.tenant_id == self.tenant_id)
            .group_by(Contact.temperature)
        )
        return {temp: count for temp, count in rows.all()}

    async def _count(self, stmt) -> int:
        return int(await self.session.scalar(stmt) or 0)


async def platform_mrr(session: AsyncSession) -> dict:
    """Platform-wide MRR + churn proxy (§08), across all active subscriptions."""
    active_mrr = await session.scalar(
        select(func.coalesce(func.sum(Subscription.mrr_cents), 0)).where(
            Subscription.status == "active"
        )
    )
    active = await session.scalar(
        select(func.count(Subscription.id)).where(Subscription.status == "active")
    )
    canceled = await session.scalar(
        select(func.count(Subscription.id)).where(Subscription.status == "canceled")
    )
    total = (active or 0) + (canceled or 0) or 1
    return {
        "mrr_cents": int(active_mrr or 0),
        "active_subscriptions": int(active or 0),
        "canceled_subscriptions": int(canceled or 0),
        "churn_rate": round((canceled or 0) / total, 3),
    }
