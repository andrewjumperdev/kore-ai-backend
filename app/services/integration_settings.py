"""Settings/credenciales de integraciones POR TENANT (cargadas desde el dashboard).

Cada proveedor (smtp, calendar, elevenlabs…) guarda su `config` JSONB en
tenant_integrations. Los agentes/integraciones lo resuelven por-tenant en vez de
leer el .env global.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant_integration import TenantIntegration


class IntegrationSettings:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id

    async def get(self, provider: str) -> dict:
        row = await self.session.scalar(
            select(TenantIntegration).where(
                TenantIntegration.tenant_id == self.tenant_id,
                TenantIntegration.provider == provider,
            )
        )
        return dict(row.config) if row and row.enabled else {}

    async def set(self, provider: str, patch: dict) -> dict:
        """Upsert con merge: solo pisa las claves provistas (no borra el resto)."""
        row = await self.session.scalar(
            select(TenantIntegration).where(
                TenantIntegration.tenant_id == self.tenant_id,
                TenantIntegration.provider == provider,
            )
        )
        if row is None:
            row = TenantIntegration(tenant_id=self.tenant_id, provider=provider, config={})
            self.session.add(row)
        row.config = {**(row.config or {}), **patch}
        row.enabled = True
        await self.session.flush()
        return dict(row.config)
