"""Síntesis de voz (respuestas en audio) vía ElevenLabs. Config POR-TENANT
(provider 'elevenlabs' en tenant_integrations), con fallback al .env. Skip seguro
sin api key/voice id."""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.exceptions import IntegrationError
from app.core.logging import get_logger

log = get_logger("voice")


def resolve_voice(config: dict | None) -> dict:
    c = config or {}
    return {
        "api_key": c.get("api_key") or settings.elevenlabs_api_key,
        "voice_id": c.get("voice_id") or settings.elevenlabs_voice_id,
    }


def voice_configured(cfg: dict) -> bool:
    return bool(cfg["api_key"] and cfg["voice_id"])


class VoiceProvider:
    name = "elevenlabs"

    async def synthesize(self, text: str, *, config: dict | None = None) -> bytes | None:
        cfg = resolve_voice(config)
        if not voice_configured(cfg):
            log.info("voice.skipped_no_credentials")
            return None
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{cfg['voice_id']}"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                url,
                headers={"xi-api-key": cfg["api_key"], "accept": "audio/mpeg"},
                json={"text": text, "model_id": "eleven_multilingual_v2"},
            )
        if resp.status_code >= 300:
            raise IntegrationError("ElevenLabs TTS failed", details={"body": resp.text[:300]})
        log.info("voice.synthesized", bytes=len(resp.content))
        return resp.content


voice = VoiceProvider()
