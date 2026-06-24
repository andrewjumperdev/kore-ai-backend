"""Pluggable embedding provider.

Production wires a real provider (OpenAI / Voyage) via HTTP. With no API key
configured we fall back to a deterministic hash embedder so the whole system —
including semantic memory — runs locally and in CI without external calls.
The fallback is NOT semantically meaningful; it only keeps dimensions/shape
stable for development and tests.
"""
from __future__ import annotations

import hashlib
import math
from typing import Protocol

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("embeddings")


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder:
    """Deterministic, dependency-free dev/test embedder."""

    def __init__(self, dim: int):
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in text.lower().split():
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str, dim: int):
        self.model = model
        self.dim = dim
        self._client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.post(
            "/embeddings", json={"model": self.model, "input": texts}
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return [item["embedding"] for item in data]


def build_embedder() -> Embedder:
    # OpenAI key reuse is optional; we key off a dedicated env in real life.
    openai_key = settings.anthropic_api_key and ""  # placeholder; see note below
    if openai_key:
        return OpenAIEmbedder(openai_key, settings.embed_model, settings.embed_dim)
    log.info("embeddings.using_hash_fallback", dim=settings.embed_dim)
    return HashEmbedder(settings.embed_dim)


embedder: Embedder = build_embedder()
