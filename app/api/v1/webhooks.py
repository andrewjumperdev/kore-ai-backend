"""Inbound webhooks (Capa 01 — captura). Channel webhooks turn provider payloads
into normalized inbound messages → record + emit message.received → the chain
routes the reply. Plaud exports are ingested into the CRM as structured data.

**Todos los webhooks se autentican** con un secreto compartido (ver
app.core.webhook_auth): la URL lleva el tenant_id, así que sin secreto bastaría
con adivinar un UUID para inyectar mensajes falsos en el CRM de un cliente y
disparar respuestas del LLM a nuestra costa. Además cada uno está limitado por
tasa a nivel de tenant.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.api.deps import DbSession
from app.core.config import settings
from app.core.context import set_current_tenant
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.core.ratelimit import hit
from app.core.webhook_auth import verify_capture_token, verify_webhook_token
from app.events.bus import event_bus
from app.events.types import EventName
from app.integrations.evolution import evolution_channel, instance_for_tenant
from app.integrations.plaud import PlaudConnector, PlaudExport
from app.integrations.registry import get_channel
from app.integrations.transcription import transcription
from app.services.contact_service import ContactService
from app.services.lead_service import LeadService
from app.tasks.customer_service_tasks import buffer_and_schedule

router = APIRouter()
log = get_logger("webhooks")


async def _authorize(request: Request, provider: str, tenant_id: UUID) -> None:
    """Autentica el webhook y aplica el límite de tasa por tenant."""
    verify_webhook_token(request, provider)
    await hit(
        f"webhook:{provider}:{tenant_id}",
        limit=settings.rate_limit_webhook_per_minute,
    )


@router.post("/plaud/{tenant_id}")
async def plaud_export(tenant_id: UUID, request: Request, session: DbSession):
    """Capa 01: ingest a Plaud recording (transcript + summary + action items)."""
    await _authorize(request, "plaud", tenant_id)
    set_current_tenant(tenant_id)
    payload = await request.json()
    export = PlaudExport.from_payload(payload)
    contact_id = await PlaudConnector(session, tenant_id).ingest(export)
    return {"ingested": True, "contact_id": str(contact_id)}


@router.post("/evolution/{tenant_id}")
async def evolution_inbound(tenant_id: UUID, request: Request):
    """Atención al cliente (FAUSTO): recibe WhatsApp vía Evolution, transcribe el
    audio si hace falta y lo manda al buffer de 8s (Fase 1+2). El agente responde
    desde la task del buffer."""
    await _authorize(request, "evolution", tenant_id)
    set_current_tenant(tenant_id)
    payload = await request.json()
    messages = evolution_channel.parse_webhook(payload)

    instance = instance_for_tenant(str(tenant_id))
    scheduled = 0
    for msg in messages:
        if msg.raw.get("from_me"):
            continue  # no responder a mensajes salientes propios
        is_audio = bool(msg.raw.get("is_audio"))
        content = msg.text
        if is_audio and msg.provider_message_id:
            audio = await evolution_channel.get_media_base64(
                msg.provider_message_id, instance=instance
            )
            if audio:
                content = await transcription.transcribe(audio)
        if not content:
            continue
        if await buffer_and_schedule(
            tenant_id=str(tenant_id),
            chat_id=msg.from_identity,
            content=content,
            message_id=msg.provider_message_id or "",
            is_audio=is_audio,
            push_name=msg.raw.get("push_name"),
        ):
            scheduled += 1

    return {"buffered": scheduled}


# Claves que suelen traer los formularios y las plataformas de automatización.
# Cada servicio nombra los campos a su manera y no vamos a pedirle al cliente que
# renombre nada: se aceptan los alias más comunes y se normaliza acá.
_ALIAS = {
    "full_name": ("full_name", "name", "nombre", "fullName", "first_name", "nombre_completo"),
    "email": ("email", "mail", "correo", "e-mail", "email_address"),
    "phone": ("phone", "telefono", "teléfono", "celular", "whatsapp", "phone_number", "tel"),
}


def _pick(payload: dict, campo: str) -> str | None:
    """Primer alias presente y no vacío, buscando sin distinguir mayúsculas."""
    plano = {str(k).lower().strip(): v for k, v in payload.items()}
    for alias in _ALIAS[campo]:
        valor = plano.get(alias.lower())
        if valor not in (None, "", []):
            return str(valor).strip()
    return None


@router.post("/lead/{tenant_id}")
async def inbound_lead(
    tenant_id: UUID,
    request: Request,
    session: DbSession,
    source: str = Query(default="web", max_length=64),
):
    """Captura universal de leads: la URL que el cliente pega donde quiera.

    Sirve para todo lo que pueda hacer un POST — el formulario de su web, un Zap,
    un escenario de Make, Typeform, Meta Lead Ads a través de un puente. Ese es
    el punto: no hace falta que construyamos una integración por plataforma para
    que el lead entre y arranque la cadena.

    El payload es libre y se normaliza por alias, porque cada servicio nombra los
    campos distinto (`name`, `nombre`, `fullName`…). Lo que no venga reconocido
    igual se guarda en `attributes`: preferimos conservar un dato que no
    entendemos a descartarlo.
    """
    # Token PROPIO del tenant, no el global: esta URL vive en sistemas de
    # terceros (Zapier, el formulario de su web) y el secreto global permitiría
    # inyectar leads en la cuenta de cualquier otro cliente.
    verify_capture_token(request, str(tenant_id))
    await hit(f"webhook:lead:{tenant_id}", limit=settings.rate_limit_webhook_per_minute)
    set_current_tenant(tenant_id)

    # JSON o form-encoded, según lo que mande el origen. Los dos casos de fallo
    # se distinguen a propósito: quien conecta un Zap y recibe "falta el email"
    # sobre un cuerpo que en realidad estaba mal formado, va a buscar el
    # problema donde no está.
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        try:
            payload = await request.json()
        except Exception as exc:
            raise ValidationError(
                "El cuerpo no es JSON válido",
                details={"content_type": ctype, "detalle": str(exc)[:160]},
            ) from exc
    else:
        payload = dict(await request.form())

    if not isinstance(payload, dict):
        raise ValidationError(
            "El cuerpo tiene que ser un objeto con los datos del lead",
            details={"recibido": type(payload).__name__},
        )

    email, phone = _pick(payload, "email"), _pick(payload, "phone")
    if not email and not phone:
        # Sin forma de contactarlo no es un lead: es ruido que ensuciaría el
        # pipeline y las métricas del dashboard.
        raise ValidationError(
            "El lead necesita al menos un email o un teléfono",
            details={"recibido": sorted(payload)[:12]},
        )

    conocidas = {a.lower() for grupo in _ALIAS.values() for a in grupo}
    extras = {
        str(k): str(v)[:500]
        for k, v in payload.items()
        if str(k).lower() not in conocidas and v not in (None, "", [])
    }

    lead = await LeadService(session, tenant_id).create_lead(
        full_name=_pick(payload, "full_name"),
        email=email,
        phone=phone,
        channel="whatsapp" if phone and not email else "email",
        source=source,
        attributes=extras,
    )
    log.info("webhook.lead_captured", source=source, lead_id=str(lead.id))
    return {"received": True, "lead_id": str(lead.id)}


@router.post("/{channel}/{tenant_id}")
async def inbound_message(channel: str, tenant_id: UUID, request: Request, session: DbSession):
    """Receive an inbound message from a channel provider.

    Autenticado con el secreto compartido genérico. Un proveedor que firme el
    payload (estilo Meta) debería verificar la firma sobre el cuerpo crudo con
    ``app.core.webhook_auth.verify_hmac_signature``, que es más fuerte."""
    await _authorize(request, channel, tenant_id)
    set_current_tenant(tenant_id)
    payload = await request.json()
    messages = get_channel(channel).parse_webhook(payload)
    contacts = ContactService(session, tenant_id)

    for msg in messages:
        identity = msg.from_identity
        is_email = "@" in identity
        contact, _ = await contacts.get_or_create(
            email=identity if is_email else None,
            phone=None if is_email else identity,
        )
        conversation = await contacts.get_or_create_conversation(contact.id, channel)
        await contacts.record_message(
            conversation_id=conversation.id,
            direction="inbound",
            body=msg.text,
            role="user",
            meta={"provider_message_id": msg.provider_message_id},
        )
        await event_bus.emit(
            session,
            EventName.MESSAGE_RECEIVED,
            source=channel,
            subject_type="contact",
            subject_id=str(contact.id),
            payload={
                "contact_id": str(contact.id),
                "conversation_id": str(conversation.id),
                "channel": channel,
                "message": msg.text,
                "to": identity,
            },
        )

    return {"received": len(messages)}
