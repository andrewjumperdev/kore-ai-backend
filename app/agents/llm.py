"""Thin LLM client with first-class structured output, provider-agnostic.

We deliberately avoid heavyweight agent frameworks. This wrapper does exactly
what our agents need: a system+user prompt in, validated JSON out, with token
accounting. Provider is selected by ``settings.llm_provider`` ("openai" |
"anthropic"). When no API key is configured for the active provider it returns a
deterministic stub so the platform runs end-to-end in dev/CI without network.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("llm")

_JSON_NUDGE = "\n\nRespond with a single valid JSON object and nothing else."


@dataclass
class LLMResult:
    data: dict
    raw_text: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMClient:
    def __init__(self) -> None:
        self.provider = (settings.llm_provider or "anthropic").lower()
        if self.provider == "openai":
            self.model = settings.openai_model
            self.api_key = settings.openai_api_key
        else:
            self.model = settings.llm_model
            self.api_key = settings.anthropic_api_key
        # NO cacheamos el cliente: el worker corre un event loop nuevo por task
        # (asyncio.run), y un cliente httpx global se ata al primer loop → luego
        # "Event loop is closed". Creamos (y cerramos) el cliente por llamada.
        log.info("llm.init", provider=self.provider, model=self.model, live=bool(self.api_key))

    async def complete_json(
        self, *, system: str, user: str, max_tokens: int = 1024, temperature: float = 0.3
    ) -> LLMResult:
        """Return a JSON object parsed from the model output. Routes to the
        active provider; falls back to a deterministic stub without a key."""
        if not self.api_key:
            return self._stub(system, user)
        if self.provider == "openai":
            return await self._complete_openai(system, user, max_tokens, temperature)
        return await self._complete_anthropic(system, user, max_tokens, temperature)

    async def _complete_openai(
        self, system: str, user: str, max_tokens: int, temperature: float
    ) -> LLMResult:
        # response_format=json_object forces strictly-parseable JSON (the prompt
        # already contains the word "JSON", which the API requires).
        from openai import AsyncOpenAI

        async with AsyncOpenAI(api_key=self.api_key) as client:
            resp = await client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system + _JSON_NUDGE},
                    {"role": "user", "content": user},
                ],
            )
        text = resp.choices[0].message.content or "{}"
        usage = resp.usage
        return LLMResult(
            data=self._safe_parse(text),
            raw_text=text,
            input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
        )

    async def _complete_anthropic(
        self, system: str, user: str, max_tokens: int, temperature: float
    ) -> LLMResult:
        from anthropic import AsyncAnthropic

        # Prefill the assistant turn with '{' so the response is reliably parseable.
        async with AsyncAnthropic(api_key=self.api_key) as client:
            message = await client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system + _JSON_NUDGE,
                messages=[
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": "{"},
                ],
            )
        text = "{" + "".join(
            block.text for block in message.content if block.type == "text"
        )
        return LLMResult(
            data=self._safe_parse(text),
            raw_text=text,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )

    @staticmethod
    def _safe_parse(text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
            log.warning("llm.json_parse_failed", preview=text[:200])
            return {"error": "unparseable_output", "raw": text[:500]}

    @staticmethod
    def _stub(system: str, user: str) -> LLMResult:
        """Deterministic offline response so the whole chain works without an API
        key. Includes the union of fields the agents read; each agent picks the
        ones it needs in shape_result."""
        data = {
            "reply": "¡Gracias por escribir! Contame un poco qué estás buscando "
            "para orientarte mejor.",
            "summary": "Diagnóstico inicial completado para el cliente.",
            "intent": "engage",
            # qualification / sdr
            "initial_temperature": "warm",
            "temperature": "warm",
            "can_classify": True,
            "clarifying_question": None,
            "needs_qualification": True,
            # followup
            "should_send": True,
            "next_followup_in_days": 3,
            "stop_sequence": False,
            "price_signal": False,
            # proposal / content
            "executive_summary": "Resumen ejecutivo de la propuesta para revisión humana.",
            "needs_human": False,
            "enable_modules": ["sdr", "qualification", "followup", "proposal", "content", "onboarding"],
            "_stub": True,
        }
        return LLMResult(data=data, raw_text=json.dumps(data), input_tokens=0, output_tokens=0)


llm = LLMClient()
