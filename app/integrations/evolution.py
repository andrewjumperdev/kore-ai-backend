"""Canal WhatsApp vía Evolution API (el que usa el flujo FAUSTO), multi-tenant.

Dos partes:
  • EvolutionChannel — enviar/recibir mensajes de UNA instancia.
  • EvolutionAdmin   — crear instancias, leer el QR y el estado de conexión. Es lo
    que usa el dashboard para que cada cliente conecte SU número.

Cada tenant tiene su propia instancia (`instance_for_tenant`). La API key global
(admin) autoriza todas las instancias. Skip seguro sin credenciales.
"""
from __future__ import annotations

import base64

import httpx

from app.core.config import settings
from app.core.exceptions import IntegrationError
from app.core.logging import get_logger
from app.integrations.base import Channel, InboundMessage, OutboundResult

log = get_logger("evolution")

# Eventos del webhook que nos interesan (mensajes entrantes).
_WEBHOOK_EVENTS = ["MESSAGES_UPSERT"]


def instance_for_tenant(tenant_id: str) -> str:
    """Nombre determinístico de la instancia de Evolution de un cliente."""
    return f"kore-{tenant_id}"


def _base() -> str:
    return settings.evolution_api_url.rstrip("/")


def _enabled() -> bool:
    return bool(settings.evolution_api_url and settings.evolution_api_key)


def _headers() -> dict:
    return {"apikey": settings.evolution_api_key}


class EvolutionChannel(Channel):
    name = "evolution"

    @property
    def enabled(self) -> bool:
        return _enabled()

    async def send(
        self, *, to: str, body: str, meta: dict | None = None, instance: str | None = None
    ) -> OutboundResult:
        if not self.enabled:
            log.info("evolution.send_skipped_no_credentials", to=to)
            return OutboundResult("evolution", None, "skipped", {"reason": "no_credentials"})
        inst = instance or settings.evolution_instance
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{_base()}/message/sendText/{inst}",
                headers=_headers(),
                json={"number": to, "text": body},
            )
        if resp.status_code >= 300:
            raise IntegrationError("Evolution send failed", details={"body": resp.text[:300]})
        data = resp.json()
        return OutboundResult("evolution", str(data.get("key", {}).get("id")), "sent", data)

    async def send_audio(self, *, to: str, audio: bytes, instance: str | None = None) -> OutboundResult:
        if not self.enabled:
            return OutboundResult("evolution", None, "skipped", {"reason": "no_credentials"})
        inst = instance or settings.evolution_instance
        b64 = base64.b64encode(audio).decode()
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{_base()}/message/sendWhatsAppAudio/{inst}",
                headers=_headers(),
                json={"number": to, "audio": b64},
            )
        if resp.status_code >= 300:
            raise IntegrationError("Evolution send_audio failed", details={"body": resp.text[:300]})
        return OutboundResult("evolution", None, "sent", resp.json())

    async def get_media_base64(self, message_id: str, *, instance: str | None = None) -> bytes | None:
        """Descarga el audio de un mensaje (equivale a 'Obtener Audio' de FAUSTO)."""
        if not self.enabled:
            return None
        inst = instance or settings.evolution_instance
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{_base()}/chat/getBase64FromMediaMessage/{inst}",
                headers=_headers(),
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
                    "from_me": key.get("fromMe", False),
                    "data": data,
                },
            )
        ]


class EvolutionAdmin:
    """Provisioning de instancias por cliente para el flujo de conexión del dashboard."""

    @property
    def enabled(self) -> bool:
        return _enabled()

    def webhook_url(self, tenant_id: str) -> str:
        url = f"{settings.public_base_url.rstrip('/')}/api/v1/webhooks/evolution/{tenant_id}"
        if settings.evolution_webhook_token:
            url += f"?token={settings.evolution_webhook_token}"
        return url

    async def ensure_instance(self, tenant_id: str) -> dict:
        """Crea la instancia del cliente si no existe, con el webhook apuntando a
        nuestro backend. Idempotente: si ya existe, sólo (re)setea el webhook."""
        inst = instance_for_tenant(tenant_id)
        hook = self.webhook_url(tenant_id)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_base()}/instance/create",
                headers=_headers(),
                json={
                    "instanceName": inst,
                    "qrcode": True,
                    "integration": "WHATSAPP-BAILEYS",
                    "webhook": {
                        "url": hook,
                        "enabled": True,
                        "base64": True,
                        "events": _WEBHOOK_EVENTS,
                    },
                },
            )
            # 403/409 = ya existe → re-set del webhook por las dudas.
            if resp.status_code in (403, 409):
                await client.post(
                    f"{_base()}/webhook/set/{inst}",
                    headers=_headers(),
                    json={"webhook": {"enabled": True, "url": hook, "base64": True, "events": _WEBHOOK_EVENTS}},
                )
                return {"instance": inst, "created": False}
            if resp.status_code >= 300:
                raise IntegrationError("Evolution create_instance failed", details={"body": resp.text[:300]})
        return {"instance": inst, "created": True, "raw": resp.json()}

    async def connect(self, tenant_id: str) -> dict:
        """Devuelve el QR (base64) y el pairing code para vincular el número."""
        inst = instance_for_tenant(tenant_id)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{_base()}/instance/connect/{inst}", headers=_headers())
        if resp.status_code >= 300:
            raise IntegrationError("Evolution connect failed", details={"body": resp.text[:300]})
        data = resp.json()
        qr = data.get("base64") or (data.get("qrcode") or {}).get("base64")
        return {"instance": inst, "qr_base64": qr, "pairing_code": data.get("pairingCode")}

    async def state(self, tenant_id: str) -> dict:
        """Estado de conexión: open (conectado) | connecting | close."""
        inst = instance_for_tenant(tenant_id)
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{_base()}/instance/connectionState/{inst}", headers=_headers())
        if resp.status_code == 404:
            return {"instance": inst, "state": "not_created"}
        if resp.status_code >= 300:
            raise IntegrationError("Evolution state failed", details={"body": resp.text[:300]})
        state = (resp.json().get("instance") or {}).get("state", "close")
        return {"instance": inst, "state": state}

    async def logout(self, tenant_id: str) -> dict:
        inst = instance_for_tenant(tenant_id)
        async with httpx.AsyncClient(timeout=20) as client:
            await client.delete(f"{_base()}/instance/logout/{inst}", headers=_headers())
        return {"instance": inst, "state": "close"}


evolution_channel = EvolutionChannel()
evolution_admin = EvolutionAdmin()
