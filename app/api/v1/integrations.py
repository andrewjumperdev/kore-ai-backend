"""Conexión de canales por cliente desde el dashboard.

WhatsApp (Evolution API): cada tenant crea su instancia y vincula su número
escaneando un QR. El webhook de la instancia se auto-configura apuntando a
/webhooks/evolution/{tenant_id}. Auth por API key de tenant.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import TenantId
from app.core.exceptions import IntegrationError
from app.integrations.evolution import evolution_admin

router = APIRouter()


class WhatsAppConnectOut(BaseModel):
    instance: str
    qr_base64: str | None = None
    pairing_code: str | None = None
    state: str


class WhatsAppStatusOut(BaseModel):
    instance: str
    state: str  # not_created | close | connecting | open | disabled
    connected: bool


def _not_configured() -> IntegrationError:
    return IntegrationError(
        "Evolution API no está configurado en el servidor (EVOLUTION_API_URL/KEY).",
        details={"hint": "configurar el backend o levantar el servicio evolution"},
    )


@router.post("/whatsapp/connect", response_model=WhatsAppConnectOut)
async def whatsapp_connect(tenant_id: TenantId) -> WhatsAppConnectOut:
    """Crea/asegura la instancia del cliente y devuelve el QR para escanear."""
    if not evolution_admin.enabled:
        raise _not_configured()
    tid = str(tenant_id)
    await evolution_admin.ensure_instance(tid)
    conn = await evolution_admin.connect(tid)
    st = await evolution_admin.state(tid)
    return WhatsAppConnectOut(
        instance=conn["instance"],
        qr_base64=conn.get("qr_base64"),
        pairing_code=conn.get("pairing_code"),
        state=st["state"],
    )


@router.get("/whatsapp/status", response_model=WhatsAppStatusOut)
async def whatsapp_status(tenant_id: TenantId) -> WhatsAppStatusOut:
    if not evolution_admin.enabled:
        return WhatsAppStatusOut(instance="", state="disabled", connected=False)
    st = await evolution_admin.state(str(tenant_id))
    return WhatsAppStatusOut(
        instance=st["instance"], state=st["state"], connected=st["state"] == "open"
    )


@router.post("/whatsapp/disconnect", response_model=WhatsAppStatusOut)
async def whatsapp_disconnect(tenant_id: TenantId) -> WhatsAppStatusOut:
    if not evolution_admin.enabled:
        raise _not_configured()
    st = await evolution_admin.logout(str(tenant_id))
    return WhatsAppStatusOut(instance=st["instance"], state=st["state"], connected=False)
