"""Empresa y oportunidad — las dos entidades que le faltaban al CRM.

Hasta acá un contacto era una persona suelta con una temperatura. Eso alcanza
para atender y calificar, pero no para responder "¿cuánto hay en el pipeline?"
ni "¿cuánto tardamos en cerrar?" — que es lo que Analytics necesita y por lo
que estaba vacío.

El monto va en centavos enteros, nunca en float: 0.1 + 0.2 no da 0.3 en binario
y un pipeline que no cierra por centavos es un pipeline en el que nadie confía.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

# Las etapas, en orden. `won` y `lost` son terminales: una vez ahí, la
# oportunidad sale del pipeline abierto y entra en las métricas de cierre.
DEAL_STAGES = ("new", "qualified", "proposal", "negotiation", "won", "lost")
OPEN_STAGES = ("new", "qualified", "proposal", "negotiation")
CLOSED_STAGES = ("won", "lost")


class Company(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """La organización detrás de un contacto.

    ``domain`` es la clave de deduplicación natural —dos personas de la misma
    empresa escriben desde el mismo dominio de mail— pero es opcional: en
    inmobiliaria o retail el comprador es una persona física y no hay dominio.
    Por eso la unicidad es sobre el nombre normalizado, con el dominio como
    dato adicional y no como identidad.
    """

    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name_key", name="uq_company_name"),
        Index("ix_company_domain", "tenant_id", "domain"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Nombre normalizado (minúsculas, sin espacios extra) para deduplicar sin
    # que "ACME S.A." y "acme s.a." convivan como dos empresas distintas.
    name_key: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class Deal(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Una oportunidad concreta de venta, con plata y fecha.

    Es lo que convierte al CRM en algo medible: un contacto caliente sin monto
    no se puede sumar, priorizar ni proyectar.
    """

    __tablename__ = "deals"
    __table_args__ = (
        Index("ix_deal_stage", "tenant_id", "stage"),
        Index("ix_deal_contact", "tenant_id", "contact_id"),
    )

    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), default="new", nullable=False, index=True)

    # Centavos. Nullable a propósito: una oportunidad recién abierta muchas
    # veces todavía no tiene monto, y poner 0 mentiría en el total del pipeline.
    amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    expected_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Cuándo pasó a won/lost. Con `created_at` da el ciclo de venta real, que es
    # la métrica que nadie puede calcular hoy.
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lost_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Quién la lleva. Es texto y no un FK a users porque el equipo del cliente
    # no vive en nuestra tabla de usuarios: son sus vendedores, no los nuestros.
    owner: Mapped[str | None] = mapped_column(String(120), nullable=True)

    attributes: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    @property
    def is_open(self) -> bool:
        return self.stage in OPEN_STAGES
