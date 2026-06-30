"""Scraping liviano del sitio de un prospecto: texto visible + colores de marca.
Port del nodo 'Limpiar codigo + colores' del flujo n8n. Sin credenciales."""
from __future__ import annotations

import re

import httpx

from app.core.logging import get_logger

log = get_logger("scraping")

_SCRIPT = re.compile(r"<script[\s\S]*?>[\s\S]*?</script>", re.I)
_STYLE = re.compile(r"<style[\s\S]*?>[\s\S]*?</style>", re.I)
_TAGS = re.compile(r"<\/?[^>]+(>|$)")
_COLOR = re.compile(r"(#(?:[0-9a-f]{3}){1,2}|rgb\([^)]+\)|rgba\([^)]+\))", re.I)


async def fetch_site(url: str, *, max_chars: int = 3000) -> dict:
    """Devuelve {text, colors}. Best-effort: ante error devuelve vacío."""
    if not url:
        return {"text": "", "colors": []}
    if not url.startswith("http"):
        url = "https://" + url
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (KORE bot)"})
        html = resp.text or ""
    except Exception as exc:  # noqa: BLE001 — scraping es best-effort
        log.info("scraping.failed", url=url, error=str(exc)[:120])
        return {"text": "", "colors": []}

    text = _TAGS.sub("", _STYLE.sub("", _SCRIPT.sub("", html)))
    text = re.sub(r"\s+", " ", text).strip()[:max_chars]
    colors = list(dict.fromkeys(_COLOR.findall(html)))[:12]  # únicos, top 12
    return {"text": text, "colors": colors}
