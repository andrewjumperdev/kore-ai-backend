"""Calendario (Google Calendar) — disponibilidad + reserva, apto para producción.

Auth: refresh-token OAuth (se mintea y cachea el access token; no vence) con
fallback a un token estático para dev. `is_slot_free` re-verifica contra el
calendario en vivo antes de agendar (anti-doble-reserva). `create_event` adjunta
un Google Meet. Sin credenciales → skip seguro.

`compute_availability` es el port compacto del algoritmo de FAUSTO: 14 días,
horarios válidos L-V, fines de semana cerrados, descontando lo ocupado.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.core.exceptions import IntegrationError
from app.core.logging import get_logger

log = get_logger("calendar")

VALID_HOURS = [
    "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
    "14:00", "14:30", "15:00", "15:30", "16:00", "16:30",
    "17:00", "17:30", "18:00", "18:30", "19:00", "19:30",
    "20:00", "20:30", "21:00", "21:30", "22:00",
]
_DAYS_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_BASE = "https://www.googleapis.com/calendar/v3"


@dataclass
class CalendarEvent:
    id: str | None
    html_link: str | None
    meet_link: str | None
    status: str
    raw: dict


class CalendarProvider:
    name = "google"

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_exp: float = 0.0

    @property
    def enabled(self) -> bool:
        has_auth = bool(
            settings.google_calendar_token
            or (settings.google_client_id and settings.google_client_secret and settings.google_refresh_token)
        )
        return bool(settings.google_calendar_id and has_auth)

    async def _access_token(self) -> str:
        """Devuelve un access token válido. Mintea vía refresh-token y cachea hasta
        ~1 min antes de expirar; si solo hay token estático, lo usa tal cual."""
        if settings.google_refresh_token and settings.google_client_id:
            if self._token and time.time() < self._token_exp - 60:
                return self._token
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    _TOKEN_URL,
                    data={
                        "client_id": settings.google_client_id,
                        "client_secret": settings.google_client_secret,
                        "refresh_token": settings.google_refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
            if resp.status_code >= 300:
                raise IntegrationError("Google token refresh failed", details={"body": resp.text[:300]})
            data = resp.json()
            self._token = data["access_token"]
            self._token_exp = time.time() + int(data.get("expires_in", 3600))
            return self._token
        return settings.google_calendar_token

    async def _headers(self) -> dict:
        return {"Authorization": f"Bearer {await self._access_token()}"}

    async def list_events(self, *, time_min: str, time_max: str) -> list[dict]:
        if not self.enabled:
            log.info("calendar.list_skipped_no_credentials")
            return []
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{_BASE}/calendars/{settings.google_calendar_id}/events",
                headers=await self._headers(),
                params={
                    "timeMin": time_min, "timeMax": time_max,
                    "singleEvents": "true", "orderBy": "startTime", "maxResults": 250,
                },
            )
        if resp.status_code >= 300:
            raise IntegrationError("Google Calendar list failed", details={"body": resp.text[:300]})
        return resp.json().get("items", [])

    async def is_slot_free(self, *, start: str, end: str) -> bool:
        """Re-verifica en vivo que el rango no se solape con ningún evento."""
        if not self.enabled:
            return True  # sin calendario no bloqueamos el flujo
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{_BASE}/freeBusy",
                headers=await self._headers(),
                json={"timeMin": start, "timeMax": end, "items": [{"id": settings.google_calendar_id}]},
            )
        if resp.status_code >= 300:
            raise IntegrationError("Google freeBusy failed", details={"body": resp.text[:300]})
        cals = resp.json().get("calendars", {})
        busy = cals.get(settings.google_calendar_id, {}).get("busy", [])
        return len(busy) == 0

    async def create_event(
        self,
        *,
        start: str,
        end: str,
        summary: str,
        description: str = "",
        attendee_email: str | None = None,
        idempotency_key: str | None = None,
    ) -> CalendarEvent:
        if not self.enabled:
            log.info("calendar.create_skipped_no_credentials", summary=summary)
            return CalendarEvent(None, None, None, "skipped", {"reason": "no_credentials"})

        body: dict = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start, "timeZone": settings.cs_timezone},
            "end": {"dateTime": end, "timeZone": settings.cs_timezone},
            "conferenceData": {
                "createRequest": {
                    "requestId": idempotency_key or f"kore-{int(time.time()*1000)}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }
        if attendee_email:
            body["attendees"] = [{"email": attendee_email}]

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{_BASE}/calendars/{settings.google_calendar_id}/events",
                headers=await self._headers(),
                params={"conferenceDataVersion": 1, "sendUpdates": "all"},
                json=body,
            )
        if resp.status_code >= 300:
            raise IntegrationError("Google Calendar create failed", details={"body": resp.text[:300]})
        data = resp.json()
        meet = data.get("hangoutLink") or _extract_meet(data)
        return CalendarEvent(data.get("id"), data.get("htmlLink"), meet, "confirmed", data)


def _extract_meet(data: dict) -> str | None:
    for ep in (data.get("conferenceData", {}) or {}).get("entryPoints", []):
        if ep.get("entryPointType") == "video":
            return ep.get("uri")
    return None


def compute_availability(events: list[dict], *, days: int = 14) -> str:
    """Port compacto del 'Procesar Disponibilidad' de FAUSTO → bloque de texto."""
    busy: dict[str, set[str]] = {}
    for ev in events:
        start = (ev.get("start") or {}).get("dateTime")
        end = (ev.get("end") or {}).get("dateTime")
        if not start:
            continue
        try:
            sd = datetime.fromisoformat(start.replace("Z", "+00:00"))
            ed = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else sd
        except ValueError:
            continue
        day = sd.date().isoformat()
        slot = busy.setdefault(day, set())
        cur = sd
        while cur < ed:
            slot.add(cur.strftime("%H:%M"))
            cur += timedelta(minutes=30)

    today = datetime.now(timezone.utc).date()
    lines = [f"📅 DISPONIBILIDAD (próximos {days} días, hora {settings.cs_timezone}):", ""]
    for i in range(days):
        d = today + timedelta(days=i)
        dow = d.weekday()  # 0=Lunes
        name = _DAYS_ES[dow]
        ds = d.isoformat()
        if dow >= 5:  # fin de semana
            lines.append(f"🚫 {name} {ds}: CERRADO (fin de semana)")
            continue
        taken = busy.get(ds, set())
        free = [h for h in VALID_HOURS if h not in taken]
        if not free:
            lines.append(f"❌ {name} {ds}: COMPLETO")
        elif len(free) <= 3:
            lines.append(f"⚠️ {name} {ds}: casi lleno — {', '.join(free)}")
        else:
            lines.append(f"✅ {name} {ds}: {', '.join(free)}")
    return "\n".join(lines)


calendar = CalendarProvider()
