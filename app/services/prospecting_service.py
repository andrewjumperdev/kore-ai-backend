"""Prospección cold email (port del flujo n8n a KORE).

import_prospects: carga la lista (web+correo). run_batch: por cada prospecto
pendiente → scrapea su web → corre el agente icebreaker → envía por SMTP → marca
'sent'/'failed'. Reutilizable desde el endpoint manual y la task horaria.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select

from app.agents.runner import AgentRunner
from app.core.config import settings
from app.core.logging import get_logger
from app.integrations.scraping import fetch_site
from app.integrations.smtp_email import resolve_smtp, smtp_sender
from app.models.prospect import Prospect
from app.services.integration_settings import IntegrationSettings

_PERSONA_KEYS = ("sender_name", "company", "cta_url")

log = get_logger("prospecting")


class ProspectingService:
    def __init__(self, session, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    async def import_prospects(self, rows: list[dict]) -> dict:
        """Inserta prospectos nuevos (dedup por email dentro del tenant)."""
        existing = set(
            await self.session.scalars(
                select(Prospect.email).where(Prospect.tenant_id == self.tenant_id)
            )
        )
        added = 0
        for r in rows:
            email = (r.get("email") or "").strip().lower()
            if not email or email in existing:
                continue
            existing.add(email)
            self.session.add(
                Prospect(
                    tenant_id=self.tenant_id,
                    email=email,
                    web=(r.get("web") or "").strip() or None,
                    company_name=(r.get("company_name") or "").strip() or None,
                    status="pending",
                )
            )
            added += 1
        await self.session.flush()
        return {"added": added, "skipped": len(rows) - added}

    async def stats(self) -> dict:
        rows = await self.session.execute(
            select(Prospect.status, func.count(Prospect.id))
            .where(Prospect.tenant_id == self.tenant_id)
            .group_by(Prospect.status)
        )
        by = {s: c for s, c in rows.all()}
        smtp_cfg = resolve_smtp(await IntegrationSettings(self.session, self.tenant_id).get("smtp"))
        return {
            "pending": by.get("pending", 0),
            "sent": by.get("sent", 0),
            "failed": by.get("failed", 0),
            "skipped": by.get("skipped", 0),
            "total": sum(by.values()),
            "smtp_configured": bool(smtp_cfg["host"] and smtp_cfg["from"]),
        }

    async def list_prospects(self, limit: int = 100) -> list[Prospect]:
        return list(
            await self.session.scalars(
                select(Prospect)
                .where(Prospect.tenant_id == self.tenant_id)
                .order_by(Prospect.created_at.desc())
                .limit(limit)
            )
        )

    async def run_batch(self, limit: int | None = None) -> dict:
        """Procesa hasta N pendientes (default = config). Devuelve resumen."""
        limit = limit or settings.prospecting_batch_size
        pending = list(
            await self.session.scalars(
                select(Prospect)
                .where(Prospect.tenant_id == self.tenant_id, Prospect.status == "pending")
                .order_by(Prospect.created_at.asc())
                .limit(limit)
            )
        )
        # Config por-tenant (desde el dashboard); fallback a .env.
        settings_store = IntegrationSettings(self.session, self.tenant_id)
        smtp_cfg = await settings_store.get("smtp")
        persona = {k: smtp_cfg[k] for k in _PERSONA_KEYS if smtp_cfg.get(k)}

        sent = failed = 0
        runner = AgentRunner(self.session, self.tenant_id)
        for p in pending:
            try:
                site = await fetch_site(p.web or "")
                run = await runner.run(
                    "icebreaker",
                    {
                        "message": f"Prospecto: {p.company_name or p.email}",
                        "site_text": site["text"],
                        "colors": site["colors"],
                        "company": p.company_name,
                        "to_email": p.email,
                        "persona": persona,
                    },
                )
                out = run.output.get("output", {}) if isinstance(run.output, dict) else {}
                subject = out.get("subject") or "Una idea para tu negocio"
                html = out.get("html") or ""
                if not html:
                    raise ValueError("el agente no devolvió HTML")
                res = await smtp_sender.send_html(to=p.email, subject=subject, html=html, config=smtp_cfg)
                p.subject, p.html = subject, html
                if res.get("status") == "sent":
                    p.status, p.sent_at = "sent", datetime.now(timezone.utc)
                    sent += 1
                else:
                    p.status, p.error = "skipped", res.get("reason", "smtp no configurado")
            except Exception as exc:  # noqa: BLE001
                p.status, p.error = "failed", str(exc)[:500]
                failed += 1
                log.warning("prospecting.failed", email=p.email, error=str(exc)[:160])
        await self.session.flush()
        log.info("prospecting.batch", processed=len(pending), sent=sent, failed=failed)
        return {"processed": len(pending), "sent": sent, "failed": failed}
