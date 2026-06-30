"""Conexión de canales por cliente desde el dashboard.

WhatsApp (Evolution API): cada tenant crea su instancia y vincula su número
escaneando un QR. El webhook de la instancia se auto-configura apuntando a
/webhooks/evolution/{tenant_id}. Auth por API key de tenant.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.agents.customer_service import CS_AGENT_DEFAULTS, merged_agent_config
from app.api.deps import DbSession, TenantId
from app.core.exceptions import IntegrationError
from app.integrations.calendar import calendar_configured, resolve_calendar
from app.integrations.evolution import evolution_admin
from app.integrations.smtp_email import resolve_smtp
from app.integrations.voice import resolve_voice, voice_configured
from app.services.integration_settings import IntegrationSettings

router = APIRouter()


# ── SMTP / Cold email (config por-tenant desde el dashboard) ─────────────────
class SmtpSettingsIn(BaseModel):
    host: str | None = None
    port: int | None = None
    user: str | None = None
    password: str | None = None
    from_email: str | None = None
    use_tls: bool | None = None
    sender_name: str | None = None
    company: str | None = None
    cta_url: str | None = None


class SmtpSettingsOut(BaseModel):
    configured: bool
    host: str = ""
    port: int = 587
    user: str = ""
    from_email: str = ""
    use_tls: bool = True
    has_password: bool = False
    sender_name: str = ""
    company: str = ""
    cta_url: str = ""


def _smtp_out(cfg: dict) -> SmtpSettingsOut:
    eff = resolve_smtp(cfg)
    return SmtpSettingsOut(
        configured=bool(eff["host"] and eff["from"]),
        host=cfg.get("host", ""),
        port=cfg.get("port", 587),
        user=cfg.get("user", ""),
        from_email=cfg.get("from", ""),
        use_tls=cfg.get("use_tls", True),
        has_password=bool(cfg.get("password")),
        sender_name=cfg.get("sender_name", ""),
        company=cfg.get("company", ""),
        cta_url=cfg.get("cta_url", ""),
    )


@router.get("/smtp", response_model=SmtpSettingsOut)
async def get_smtp(tenant_id: TenantId, session: DbSession) -> SmtpSettingsOut:
    cfg = await IntegrationSettings(session, tenant_id).get("smtp")
    return _smtp_out(cfg)


@router.put("/smtp", response_model=SmtpSettingsOut)
async def put_smtp(body: SmtpSettingsIn, tenant_id: TenantId, session: DbSession) -> SmtpSettingsOut:
    patch: dict = {}
    for field, key in (
        ("host", "host"), ("port", "port"), ("user", "user"),
        ("from_email", "from"), ("use_tls", "use_tls"),
        ("sender_name", "sender_name"), ("company", "company"), ("cta_url", "cta_url"),
    ):
        val = getattr(body, field)
        if val is not None:
            patch[key] = val
    if body.password:  # la password solo se actualiza si la mandan
        patch["password"] = body.password
    cfg = await IntegrationSettings(session, tenant_id).set("smtp", patch)
    return _smtp_out(cfg)


# ── Google Calendar (config por-tenant) ──────────────────────────────────────
class CalendarSettingsIn(BaseModel):
    calendar_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    refresh_token: str | None = None
    token: str | None = None
    timezone: str | None = None


class CalendarSettingsOut(BaseModel):
    configured: bool
    calendar_id: str = ""
    client_id: str = ""
    timezone: str = "Europe/Paris"
    has_client_secret: bool = False
    has_refresh_token: bool = False
    has_token: bool = False


def _calendar_out(cfg: dict) -> CalendarSettingsOut:
    return CalendarSettingsOut(
        configured=calendar_configured(resolve_calendar(cfg)),
        calendar_id=cfg.get("calendar_id", ""),
        client_id=cfg.get("client_id", ""),
        timezone=cfg.get("timezone", "Europe/Paris"),
        has_client_secret=bool(cfg.get("client_secret")),
        has_refresh_token=bool(cfg.get("refresh_token")),
        has_token=bool(cfg.get("token")),
    )


@router.get("/calendar", response_model=CalendarSettingsOut)
async def get_calendar(tenant_id: TenantId, session: DbSession) -> CalendarSettingsOut:
    return _calendar_out(await IntegrationSettings(session, tenant_id).get("calendar"))


@router.put("/calendar", response_model=CalendarSettingsOut)
async def put_calendar(body: CalendarSettingsIn, tenant_id: TenantId, session: DbSession) -> CalendarSettingsOut:
    patch: dict = {}
    for field in ("calendar_id", "client_id", "timezone"):
        val = getattr(body, field)
        if val is not None:
            patch[field] = val
    for secret in ("client_secret", "refresh_token", "token"):  # solo si los mandan
        val = getattr(body, secret)
        if val:
            patch[secret] = val
    cfg = await IntegrationSettings(session, tenant_id).set("calendar", patch)
    return _calendar_out(cfg)


# ── ElevenLabs / Voz (config por-tenant) ─────────────────────────────────────
class VoiceSettingsIn(BaseModel):
    api_key: str | None = None
    voice_id: str | None = None


class VoiceSettingsOut(BaseModel):
    configured: bool
    voice_id: str = ""
    has_api_key: bool = False


def _voice_out(cfg: dict) -> VoiceSettingsOut:
    return VoiceSettingsOut(
        configured=voice_configured(resolve_voice(cfg)),
        voice_id=cfg.get("voice_id", ""),
        has_api_key=bool(cfg.get("api_key")),
    )


@router.get("/elevenlabs", response_model=VoiceSettingsOut)
async def get_voice(tenant_id: TenantId, session: DbSession) -> VoiceSettingsOut:
    return _voice_out(await IntegrationSettings(session, tenant_id).get("elevenlabs"))


@router.put("/elevenlabs", response_model=VoiceSettingsOut)
async def put_voice(body: VoiceSettingsIn, tenant_id: TenantId, session: DbSession) -> VoiceSettingsOut:
    patch: dict = {}
    if body.voice_id is not None:
        patch["voice_id"] = body.voice_id
    if body.api_key:
        patch["api_key"] = body.api_key
    cfg = await IntegrationSettings(session, tenant_id).set("elevenlabs", patch)
    return _voice_out(cfg)


# ── Agente de WhatsApp (persona/comportamiento, totalmente editable) ──────────
_AGENT_FIELDS = tuple(CS_AGENT_DEFAULTS.keys())


class AgentSettingsIn(BaseModel):
    agent_name: str | None = None
    company_name: str | None = None
    company_tagline: str | None = None
    objective: str | None = None
    about: str | None = None
    proof_points: str | None = None
    meeting_duration: str | None = None
    availability: str | None = None
    tone: str | None = None
    emojis: str | None = None
    language: str | None = None
    flow: str | None = None
    rules: str | None = None


class AgentSettingsOut(AgentSettingsIn):
    configured: bool = False


@router.get("/whatsapp-agent", response_model=AgentSettingsOut)
async def get_agent(tenant_id: TenantId, session: DbSession) -> AgentSettingsOut:
    cfg = await IntegrationSettings(session, tenant_id).get("whatsapp_agent")
    # Devolvemos el merge con los defaults FAUSTO para pre-llenar el panel.
    return AgentSettingsOut(**merged_agent_config(cfg), configured=bool(cfg))


@router.put("/whatsapp-agent", response_model=AgentSettingsOut)
async def put_agent(body: AgentSettingsIn, tenant_id: TenantId, session: DbSession) -> AgentSettingsOut:
    patch = {f: getattr(body, f) for f in _AGENT_FIELDS if getattr(body, f) is not None}
    cfg = await IntegrationSettings(session, tenant_id).set("whatsapp_agent", patch)
    return AgentSettingsOut(**merged_agent_config(cfg), configured=bool(cfg))


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
