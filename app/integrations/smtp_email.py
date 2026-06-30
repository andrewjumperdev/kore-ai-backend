"""Envío de cold emails por SMTP propio (como el flujo n8n). Usa smtplib de la
stdlib en un thread para no bloquear el loop. Skip seguro sin host configurado."""
from __future__ import annotations

import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings
from app.core.exceptions import IntegrationError
from app.core.logging import get_logger

log = get_logger("smtp")


def resolve_smtp(config: dict | None) -> dict:
    """Resuelve la config SMTP efectiva: la del tenant (config) y, si falta una
    clave, el .env global como fallback."""
    c = config or {}
    return {
        "host": c.get("host") or settings.smtp_host,
        "port": int(c.get("port") or settings.smtp_port),
        "user": c.get("user") or settings.smtp_user,
        "password": c.get("password") or settings.smtp_password,
        "from": c.get("from") or settings.smtp_from,
        "use_tls": c.get("use_tls", settings.smtp_use_tls),
    }


class SmtpSender:
    name = "smtp"

    async def send_html(self, *, to: str, subject: str, html: str, config: dict | None = None) -> dict:
        cfg = resolve_smtp(config)
        if not (cfg["host"] and cfg["from"]):
            log.info("smtp.skipped_no_credentials", to=to)
            return {"status": "skipped", "reason": "no_credentials"}
        return await asyncio.to_thread(self._send, cfg, to, subject, html)

    def _send(self, cfg: dict, to: str, subject: str, html: str) -> dict:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = cfg["from"]
        msg["To"] = to
        msg.attach(MIMEText(html, "html", "utf-8"))

        host, port = cfg["host"], cfg["port"]
        try:
            if port == 465:
                server = smtplib.SMTP_SSL(host, port, timeout=30)
            else:
                server = smtplib.SMTP(host, port, timeout=30)
                if cfg["use_tls"]:
                    server.starttls()
            with server:
                if cfg["user"]:
                    server.login(cfg["user"], cfg["password"])
                server.send_message(msg)
        except Exception as exc:  # noqa: BLE001
            raise IntegrationError("SMTP send failed", details={"error": str(exc)[:300]}) from exc

        log.info("smtp.sent", to=to)
        return {"status": "sent"}


smtp_sender = SmtpSender()
