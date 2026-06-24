"""Email channel via Resend (swap for SendGrid by changing this one file)."""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.exceptions import IntegrationError
from app.core.logging import get_logger
from app.integrations.base import Channel, InboundMessage, OutboundResult

log = get_logger("email")


class EmailChannel(Channel):
    name = "email"

    async def send(self, *, to: str, body: str, meta: dict | None = None) -> OutboundResult:
        if not settings.resend_api_key:
            log.info("email.send_skipped_no_credentials", to=to)
            return OutboundResult("resend", None, "skipped", {"reason": "no_credentials"})

        subject = (meta or {}).get("subject", "A quick note from us")
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": settings.email_from,
                    "to": [to],
                    "subject": subject,
                    "text": body,
                },
            )
        if resp.status_code >= 300:
            raise IntegrationError("Email send failed", details={"body": resp.text})
        data = resp.json()
        return OutboundResult("resend", data.get("id"), "sent", data)

    def parse_webhook(self, payload: dict) -> list[InboundMessage]:
        # Inbound email parsing (e.g. Resend inbound / SES) normalized here.
        return [
            InboundMessage(
                channel="email",
                from_identity=payload.get("from", ""),
                text=payload.get("text", ""),
                provider_message_id=payload.get("message_id"),
                raw=payload,
            )
        ]


email_channel = EmailChannel()
