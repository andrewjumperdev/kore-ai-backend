"""Orquestación del agente de atención al cliente (flujo FAUSTO en KORE).

Capa "Fase 3" del flujo: combina el contexto, inyecta disponibilidad, corre el
agente `customer_service` (puro) y EJECUTA sus efectos: reserva en Google Calendar
+ email de confirmación. Reutilizable desde el chat web (endpoint) y desde la
task del buffer de WhatsApp.

Booking apto para producción (equivale a Reservar_Slot → Agendar → Confirmar →
send_email de FAUSTO):
  • Lock del slot en Redis (3 min) para evitar doble-reserva concurrente.
  • Re-verificación en vivo contra el calendario (freeBusy) antes de crear.
  • Evento con Google Meet + email de confirmación.
  • Idempotencia por (tenant, email, slot) para que un retry no duplique el evento.
  • Si el slot se ocupó entre que se propuso y se confirmó, se reescribe la
    respuesta ofreciendo otros horarios.

El buffer anti-mensajes-múltiples (Fase 2) vive en customer_service_tasks.py.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

import redis.asyncio as aioredis

from app.agents.runner import AgentRunner
from app.core.config import settings
from app.core.logging import get_logger
from app.integrations.calendar import calendar, compute_availability
from app.integrations.email import email_channel

log = get_logger("customer_service")

_SLOT_LOCK_TTL = 180   # hold temporal del slot (Reservar_Slot: 3 min)
_BOOKED_TTL = 86_400   # marca de idempotencia por 24h


class CustomerServiceService:
    def __init__(self, session, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    async def availability_text(self) -> str:
        now = datetime.now(timezone.utc)
        events = await calendar.list_events(
            time_min=now.isoformat(),
            time_max=(now + timedelta(days=30)).isoformat(),
        )
        return compute_availability(events)

    async def respond(
        self,
        *,
        text: str,
        contact_id: UUID | None = None,
        push_name: str | None = None,
        channel: str = "web",
    ) -> dict:
        """Corre el agente sobre `text` (ya combinado) y ejecuta la reserva si el
        agente la confirmó. Devuelve {reply, intent, booking, booking_result}."""
        availability = await self.availability_text()
        payload: dict = {
            "message": text,
            "push_name": push_name,
            "availability": availability,
            "channel": channel,
        }
        if contact_id:
            payload["contact_id"] = str(contact_id)

        run = await AgentRunner(self.session, self.tenant_id).run("customer_service", payload)
        out = run.output or {}
        data = out.get("output", {}) if isinstance(out.get("output"), dict) else {}
        reply = out.get("reply") or data.get("reply") or ""
        booking = data.get("booking") or {}

        booking_result = await self._maybe_book(booking)
        reply = self._adjust_reply(reply, booking_result, availability)

        return {
            "reply": reply,
            "intent": data.get("intent"),
            "booking": booking,
            "booking_result": booking_result,
            "run_id": str(run.id),
        }

    # ── Booking (Fase 3) ─────────────────────────────────────────────────────

    async def _maybe_book(self, booking: dict) -> dict | None:
        if booking.get("action") != "confirm" or not booking.get("selected_slot"):
            return None
        if not calendar.enabled:
            return {"status": "calendar_not_configured"}

        start = str(booking["selected_slot"])
        try:
            sd = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            log.warning("cs.invalid_slot", slot=start)
            return {"status": "invalid_slot"}
        end_iso = (sd + timedelta(minutes=settings.cs_meeting_minutes)).isoformat()

        email = (booking.get("attendee_email") or "").strip().lower()
        slot_id = re.sub(r"[^0-9T]", "", start)[:15]
        lock_key = f"cs:slot:{self.tenant_id}:{slot_id}"
        booked_key = f"cs:booked:{self.tenant_id}:{email}:{slot_id}"
        idem = f"kore-{self.tenant_id}-{slot_id}"

        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            # Idempotencia: ¿ya agendamos esta misma reunión? (retry)
            prev = await r.get(booked_key)
            if prev:
                return {"status": "already_booked", "event_id": prev}

            # Reservar_Slot: hold temporal anti-concurrencia.
            if not await r.set(lock_key, "1", nx=True, ex=_SLOT_LOCK_TTL):
                log.info("cs.slot_locked", slot=slot_id)
                return {"status": "slot_taken"}

            # Re-verificación en vivo (pudo ocuparse desde que se propuso).
            if not await calendar.is_slot_free(start=start, end=end_iso):
                return {"status": "slot_taken"}

            name = booking.get("attendee_name") or "Cliente"
            summary = booking.get("summary") or f"{name} — Llamada de descubrimiento"
            description = (
                "Reunión agendada por el agente de atención al cliente.\n"
                f"Cliente: {name}\nEmpresa: {booking.get('attendee_company') or '-'}\n"
                f"Email: {email or '-'}"
            )
            event = await calendar.create_event(
                start=start, end=end_iso, summary=summary, description=description,
                attendee_email=email or None, idempotency_key=idem,
            )

            # Confirmar_Reserva: marca permanente de idempotencia.
            if event.status == "confirmed":
                await r.set(booked_key, event.id or "1", ex=_BOOKED_TTL)

            email_status = None
            if email and event.status == "confirmed":
                res = await email_channel.send(
                    to=email,
                    body=(
                        f"Hola {name},\n\nTu reunión quedó confirmada para {start} "
                        f"({settings.cs_timezone}).\n"
                        + (f"Link: {event.meet_link}\n" if event.meet_link else "")
                        + "\n¡Nos vemos!"
                    ),
                    meta={"subject": "Confirmación de tu reunión"},
                )
                email_status = res.status

            log.info("cs.booked", status=event.status, event_id=event.id, meet=bool(event.meet_link))
            return {
                "status": event.status,
                "event_id": event.id,
                "link": event.html_link,
                "meet": event.meet_link,
                "email": email_status,
            }
        finally:
            await r.aclose()

    @staticmethod
    def _adjust_reply(reply: str, booking_result: dict | None, availability: str) -> str:
        """Ajusta la respuesta del agente según el resultado real de la reserva."""
        if not booking_result:
            return reply
        st = booking_result.get("status")
        if st == "slot_taken":
            options = "\n".join(
                ln for ln in availability.splitlines() if ln.startswith("✅") or ln.startswith("⚠️")
            )[:600]
            return (
                "¡Uy! Justo se ocupó ese horario. Te paso otras opciones disponibles:\n"
                + (options or "Decime qué día te queda mejor y vemos.")
            )
        if st == "confirmed" and booking_result.get("meet"):
            return f"{reply}\n\n✅ Reunión agendada. Link: {booking_result['meet']}"
        return reply
