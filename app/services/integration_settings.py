"""Settings/credenciales de integraciones POR TENANT (cargadas desde el dashboard).

Cada proveedor (smtp, calendar, elevenlabs…) guarda su `config` JSONB en
tenant_integrations. Los agentes/integraciones lo resuelven por-tenant en vez de
leer el .env global.

Las claves sensibles (password, *_token, *_secret…) se cifran al persistir y se
descifran al leer — ver app.core.crypto. El resto del código sigue viendo dicts
en claro, así que no hay que tocar los consumidores.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_config, encrypt_config
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
        return decrypt_config(dict(row.config)) if row and row.enabled else {}

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
        # El merge se hace sobre los valores cifrados; `patch` se cifra antes de
        # entrar para que nada sensible toque la base en claro.
        row.config = {**(row.config or {}), **encrypt_config(patch)}
        row.enabled = True
        await self.session.flush()
        return decrypt_config(dict(row.config))
