"""Transcripción de audio (notas de voz entrantes) vía OpenAI Whisper.

Patrón "enchufable": si no hay OPENAI_API_KEY, hace skip seguro devolviendo "".
Usado por CustomerServiceService antes de bufferizar, igual que FAUSTO (transcribe
ANTES del buffer para unificar texto+audio).
"""
from __future__ import annotations

import io

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("transcription")


class TranscriptionProvider:
    name = "openai-whisper"

    @property
    def enabled(self) -> bool:
        return bool(settings.openai_api_key)

    async def transcribe(self, audio: bytes, *, filename: str = "audio.ogg") -> str:
        if not self.enabled:
            log.info("transcription.skipped_no_credentials")
            return ""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        buf = io.BytesIO(audio)
        buf.name = filename
        resp = await client.audio.transcriptions.create(model="whisper-1", file=buf)
        text = getattr(resp, "text", "") or ""
        log.info("transcription.done", chars=len(text))
        return text


transcription = TranscriptionProvider()
