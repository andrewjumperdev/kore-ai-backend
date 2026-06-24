"""Síntesis de voz (respuestas en audio) vía ElevenLabs.

Patrón "enchufable": si no hay ELEVENLABS_API_KEY/voice id, hace skip seguro
devolviendo None y el flujo responde en texto.
"""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.exceptions import IntegrationError
from app.core.logging import get_logger

log = get_logger("voice")


class VoiceProvider:
    name = "elevenlabs"

    @property
    def enabled(self) -> bool:
        return bool(settings.elevenlabs_api_key and settings.elevenlabs_voice_id)

    async def synthesize(self, text: str, *, voice_id: str | None = None) -> bytes | None:
        if not self.enabled:
            log.info("voice.skipped_no_credentials")
            return None
        vid = voice_id or settings.elevenlabs_voice_id
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                url,
                headers={
                    "xi-api-key": settings.elevenlabs_api_key,
                    "accept": "audio/mpeg",
                },
                json={"text": text, "model_id": "eleven_multilingual_v2"},
            )
        if resp.status_code >= 300:
            raise IntegrationError("ElevenLabs TTS failed", details={"body": resp.text[:300]})
        log.info("voice.synthesized", bytes=len(resp.content))
        return resp.content


voice = VoiceProvider()
