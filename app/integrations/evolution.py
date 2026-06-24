"""Canal WhatsApp vía Evolution API (el que usa el flujo FAUSTO).

`parse_webhook` entiende el payload de Evolution (data.key.remoteJid, pushName,
messageType, message.conversation / extendedTextMessage.text). Los mensajes de
audio se marcan en `raw` (messageType=audioMessage) para que el flujo los
transcriba antes de bufferizar.

Skip seguro sin credenciales (EVOLUTION_API_URL/KEY).
"""
from __future__ import annotations

import base64

import httpx

from app.core.config import settings
from app.core.exceptions import IntegrationError
from app.core.logging import get_logger
from app.integrations.base import Channel, InboundMessage, OutboundResult

log = get_logger("evolution")


class EvolutionChannel(Channel):
    name = "evolution"

    @property
    def enabled(self) -> bool:
        return bool(settings.evolution_api_url and settings.evolution_api_key)

    async def send(self, *, to: str, body: str, meta: dict | None = None) -> OutboundResult:
        if not self.enabled:
            log.info("evolution.send_skipped_no_credentials", to=to)
            return OutboundResult("evolution", None, "skipped", {"reason": "no_credentials"})
        inst = settings.evolution_instance
        url = f"{settings.evolution_api_url.rstrip('/')}/message/sendText/{inst}"
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                url,
                headers={"apikey": settings.evolution_api_key},
                json={"number": to, "text": body},
            )
        if resp.status_code >= 300:
            raise IntegrationError("Evolution send failed", details={"body": resp.text[:300]})
        data = resp.json()
        return OutboundResult("evolution", str(data.get("key", {}).get("id")), "sent", data)

    async def send_audio(self, *, to: str, audio: bytes) -> OutboundResult:
        if not self.enabled:
            return OutboundResult("evolution", None, "skipped", {"reason": "no_credentials"})
        inst = settings.evolution_instance
        url = f"{settings.evolution_api_url.rstrip('/')}/message/sendWhatsAppAudio/{inst}"
        b64 = base64.b64encode(audio).decode()
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                url,
                headers={"apikey": settings.evolution_api_key},
                json={"number": to, "audio": b64},
            )
        if resp.status_code >= 300:
            raise IntegrationError("Evolution send_audio failed", details={"body": resp.text[:300]})
        return OutboundResult("evolution", None, "sent", resp.json())

    async def get_media_base64(self, message_id: str) -> bytes | None:
        """Descarga el audio de un mensaje (equivale a 'Obtener Audio' de FAUSTO)."""
        if not self.enabled:
            return None
        inst = settings.evolution_instance
        url = f"{settings.evolution_api_url.rstrip('/')}/chat/getBase64FromMediaMessage/{inst}"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                url,
                headers={"apikey": settings.evolution_api_key},
                json={"message": {"key": {"id": message_id}}},
            )
        if resp.status_code >= 300:
            raise IntegrationError("Evolution get_media failed", details={"body": resp.text[:300]})
        b64 = resp.json().get("base64", "")
        return base64.b64decode(b64) if b64 else None

    def parse_webhook(self, payload: dict) -> list[InboundMessage]:
        data = payload.get("data", payload)
        key = data.get("key", {})
        message = data.get("message", {}) or {}
        text = message.get("conversation") or (message.get("extendedTextMessage") or {}).get("text") or ""
        return [
            InboundMessage(
                channel="evolution",
                from_identity=key.get("remoteJid", ""),
                text=text,
                provider_message_id=key.get("id"),
                raw={
                    "message_type": data.get("messageType"),
                    "push_name": data.get("pushName"),
                    "timestamp": data.get("messageTimestamp"),
                    "is_audio": data.get("messageType") == "audioMessage",
                    "data": data,
                },
            )
        ]


evolution_channel = EvolutionChannel()
