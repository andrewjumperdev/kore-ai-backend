from __future__ import annotations

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class TenantIntegration(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Configuración/credenciales de una integración, POR TENANT, cargadas desde
    el dashboard (Integraciones). `config` es un JSONB con lo que necesite cada
    proveedor (smtp, calendar, elevenlabs…). Los secretos viven server-side."""

    __tablename__ = "tenant_integrations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_tenant_integration"),
    )

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
