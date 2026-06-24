"""Channel abstraction. Every outbound provider implements this interface so
agents and the runner stay provider-agnostic."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class OutboundResult:
    provider: str
    provider_message_id: str | None
    status: str  # sent | queued | failed
    raw: dict


@dataclass
class InboundMessage:
    """Normalized shape produced by each channel's webhook parser."""

    channel: str
    from_identity: str   # normalized phone/email
    text: str
    provider_message_id: str | None
    raw: dict


class Channel(ABC):
    name: str

    @abstractmethod
    async def send(self, *, to: str, body: str, meta: dict | None = None) -> OutboundResult: ...

    @abstractmethod
    def parse_webhook(self, payload: dict) -> list[InboundMessage]: ...
