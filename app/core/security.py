"""Credenciales de tenant: API keys hasheadas.

Guardamos solo el hash. La key cruda (``kore_<random>``) se le muestra al dueño
una única vez, al crear el tenant.

Nota: acá vivían además helpers de JWT y de hashing de passwords. Se quitaron
porque ningún endpoint los usaba — la identidad humana la maneja Supabase en el
frontend, y el backend solo ve API keys de tenant. Un camino de autenticación
que nadie ejercita es superficie de ataque sin contraparte de valor. Si algún
día hace falta un login propio, se reintroduce junto con su endpoint.
"""
from __future__ import annotations

import hashlib
import secrets


def generate_api_key() -> tuple[str, str]:
    """Return (raw_key, hashed_key)."""
    raw = f"kore_{secrets.token_urlsafe(32)}"
    return raw, hash_api_key(raw)


def hash_api_key(raw: str) -> str:
    """SHA-256 a secas, sin salt ni KDF, y está bien: la key tiene 256 bits de
    entropía generados por nosotros, así que no hay diccionario que atacar (a
    diferencia de un password elegido por una persona)."""
    return hashlib.sha256(raw.encode()).hexdigest()
