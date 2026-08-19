# syntax=docker/dockerfile:1

# ── Build ────────────────────────────────────────────────────────────
# Las herramientas de compilación (build-essential son ~400 MB) se quedan acá:
# la imagen final solo recibe el virtualenv ya resuelto.
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
# Solo el manifiesto: así la capa de dependencias se cachea y no se reinstala
# con cada cambio de código. Sin el extra [dev] — pytest, ruff y mypy no tienen
# nada que hacer en producción (y son superficie extra).
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# ── Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY . .

# Aseguramos el bit de ejecución del entrypoint (git puede perderlo según el SO).
RUN chmod +x /app/docker/entrypoint.sh \
    && useradd --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# El healthcheck NO va acá. Esta imagen sirve para los tres roles (api, worker,
# scheduler) y solo `api` levanta un servidor HTTP: definido a nivel de imagen,
# worker y scheduler quedaban permanentemente "unhealthy". Un contenedor que
# miente sobre su salud es peor que uno sin chequeo — tapa el problema real
# cuando aparece. Va por servicio, en docker-compose.prod.yml.

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["api"]
