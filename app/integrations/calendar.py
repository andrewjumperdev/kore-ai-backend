"""Calendario (Google Calendar) — disponibilidad + reserva, config POR-TENANT.

La config (calendar_id + auth refresh-token o token estático + timezone) sale de
`tenant_integrations` (provider 'calendar'), con fallback al .env. Cada método
acepta `config`; el access token se mintea/cachea por refresh_token. Sin config
hace skip seguro.
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


def resolve_calendar(config: dict | None) -> dict:
    c = config or {}
    return {
        "calendar_id": c.get("calendar_id") or settings.google_calendar_id,
        "client_id": c.get("client_id") or settings.google_client_id,
        "client_secret": c.get("client_secret") or settings.google_client_secret,
        "refresh_token": c.get("refresh_token") or settings.google_refresh_token,
        "token": c.get("token") or settings.google_calendar_token,
        "timezone": c.get("timezone") or settings.cs_timezone,
    }


def calendar_configured(cfg: dict) -> bool:
    has_auth = bool(
        cfg["token"] or (cfg["client_id"] and cfg["client_secret"] and cfg["refresh_token"])
    )
    return bool(cfg["calendar_id"] and has_auth)


class CalendarProvider:
    name = "google"

    def __init__(self) -> None:
        self._tokens: dict[str, tuple[str, float]] = {}  # refresh_token → (access, exp)

    async def _access_token(self, cfg: dict) -> str:
        rt = cfg["refresh_token"]
        if rt and cfg["client_id"]:
            cached = self._tokens.get(rt)
            if cached and time.time() < cached[1] - 60:
                return cached[0]
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    _TOKEN_URL,
                    data={
                        "client_id": cfg["client_id"],
                        "client_secret": cfg["client_secret"],
                        "refresh_token": rt,
                        "grant_type": "refresh_token",
                    },
                )
            if resp.status_code >= 300:
                raise IntegrationError("Google token refresh failed", details={"body": resp.text[:300]})
            data = resp.json()
            self._tokens[rt] = (data["access_token"], time.time() + int(data.get("expires_in", 3600)))
            return data["access_token"]
        return cfg["token"]

    async def _headers(self, cfg: dict) -> dict:
        return {"Authorization": f"Bearer {await self._access_token(cfg)}"}

    async def list_events(self, *, time_min: str, time_max: str, config: dict | None = None) -> list[dict]:
        cfg = resolve_calendar(config)
        if not calendar_configured(cfg):
            log.info("calendar.list_skipped_no_credentials")
            return []
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{_BASE}/calendars/{cfg['calendar_id']}/events",
                headers=await self._headers(cfg),
                params={
                    "timeMin": time_min, "timeMax": time_max,
                    "singleEvents": "true", "orderBy": "startTime", "maxResults": 250,
                },
            )
        if resp.status_code >= 300:
            raise IntegrationError("Google Calendar list failed", details={"body": resp.text[:300]})
        return resp.json().get("items", [])

    async def is_slot_free(self, *, start: str, end: str, config: dict | None = None) -> bool:
        cfg = resolve_calendar(config)
        if not calendar_configured(cfg):
            return True
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{_BASE}/freeBusy",
                headers=await self._headers(cfg),
                json={"timeMin": start, "timeMax": end, "items": [{"id": cfg["calendar_id"]}]},
            )
        if resp.status_code >= 300:
            raise IntegrationError("Google freeBusy failed", details={"body": resp.text[:300]})
        busy = resp.json().get("calendars", {}).get(cfg["calendar_id"], {}).get("busy", [])
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
        config: dict | None = None,
    ) -> CalendarEvent:
        cfg = resolve_calendar(config)
        if not calendar_configured(cfg):
            log.info("calendar.create_skipped_no_credentials", summary=summary)
            return CalendarEvent(None, None, None, "skipped", {"reason": "no_credentials"})

        body: dict = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start, "timeZone": cfg["timezone"]},
            "end": {"dateTime": end, "timeZone": cfg["timezone"]},
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
                f"{_BASE}/calendars/{cfg['calendar_id']}/events",
                headers=await self._headers(cfg),
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


def compute_availability(events: list[dict], *, days: int = 14, tz: str | None = None) -> str:
    """Port compacto del 'Procesar Disponibilidad' de FAUSTO → bloque de texto."""
    tz = tz or settings.cs_timezone
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
    lines = [f"📅 DISPONIBILIDAD (próximos {days} días, hora {tz}):", ""]
    for i in range(days):
        d = today + timedelta(days=i)
        dow = d.weekday()
        name = _DAYS_ES[dow]
        ds = d.isoformat()
        if dow >= 5:
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
