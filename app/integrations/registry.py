from __future__ import annotations

from app.core.exceptions import NotFoundError
from app.integrations.base import Channel
from app.integrations.email import email_channel
from app.integrations.evolution import evolution_channel
from app.integrations.whatsapp import whatsapp_channel

_CHANNELS: dict[str, Channel] = {
    whatsapp_channel.name: whatsapp_channel,
    email_channel.name: email_channel,
    evolution_channel.name: evolution_channel,
}


def get_channel(name: str) -> Channel:
    try:
        return _CHANNELS[name]
    except KeyError as exc:
        raise NotFoundError(f"Unknown channel '{name}'") from exc
