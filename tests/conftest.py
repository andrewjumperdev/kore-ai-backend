"""Fixtures compartidas.

Los tests corren sin Postgres ni Redis: el objetivo es cubrir las reglas que
protegen plata y datos (auth, webhooks, límites, cifrado, facturación), no el
driver de la base. Donde hace falta una sesión de DB se usa un doble; donde hace
falta Redis se lo apaga y se verifica el comportamiento *fail-open*.
"""
from __future__ import annotations

import os

# Debe pasar ANTES de importar app.core.config: el objeto Settings se construye
# al importarse el módulo y cachea el entorno.
os.environ.setdefault("KORE_ENV", "test")
os.environ.setdefault("KORE_RATE_LIMIT_ENABLED", "false")

import pytest  # noqa: E402

from app.core.config import Settings  # noqa: E402


@pytest.fixture
def make_settings():
    """Construye un Settings aislado, sin leer el .env del repo.

    ``_env_file=None`` es clave: sin eso los tests heredarían las credenciales
    reales del desarrollador y los asserts sobre defaults fallarían en su
    máquina pero no en CI (o al revés).
    """

    def _build(**overrides) -> Settings:
        return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]

    return _build
