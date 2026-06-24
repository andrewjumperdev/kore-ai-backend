"""WhatsApp Business (Meta Cloud API) channel."""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.exceptions import IntegrationError
from app.core.logging import get_logger
from app.integrations.base import Channel, InboundMessage, OutboundResult

log = get_logger("whatsapp")


class WhatsAppChannel(Channel):
    name = "whatsapp"

    async def send(self, *, to: str, body: str, meta: dict | None = None) -> OutboundResult:
        if not settings.whatsapp_access_token:
            log.info("whatsapp.send_skipped_no_credentials", to=to)
            return OutboundResult("whatsapp", None, "skipped", {"reason": "no_credentials"})

        url = f"{settings.whatsapp_api_url}/{settings.whatsapp_phone_number_id}/messages"
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "text",
                    "text": {"body": body},
                },
            )
        if resp.status_code >= 300:
            raise IntegrationError("WhatsApp send failed", details={"body": resp.text})
        data = resp.json()
        return OutboundResult(
            "whatsapp", data.get("messages", [{}])[0].get("id"), "sent", data
        )

    def parse_webhook(self, payload: dict) -> list[InboundMessage]:
        out: list[InboundMessage] = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    out.append(
                        InboundMessage(
                            channel="whatsapp",
                            from_identity=msg.get("from", ""),
                            text=msg.get("text", {}).get("body", ""),
                            provider_message_id=msg.get("id"),
                            raw=msg,
                        )
                    )
        return out


whatsapp_channel = WhatsAppChannel()
