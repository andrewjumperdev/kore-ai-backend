"""Authentication primitives: JWT for users, hashed API keys for tenants."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_ALGO = "HS256"


def hash_password(raw: str) -> str:
    return _pwd.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return _pwd.verify(raw, hashed)


def create_access_token(subject: str, tenant_id: str, ttl_minutes: int = 60 * 12) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "tid": tenant_id,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGO)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[_ALGO])


# ── Tenant API keys ──────────────────────────────────────────────────
# We store only a hash. The raw key (prefix.secret) is shown to the user once.

def generate_api_key() -> tuple[str, str]:
    """Return (raw_key, hashed_key)."""
    raw = f"kore_{secrets.token_urlsafe(32)}"
    return raw, hash_api_key(raw)


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
