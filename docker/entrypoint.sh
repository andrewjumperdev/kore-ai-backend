#!/usr/bin/env bash
set -euo pipefail

# Single image, three roles selected by the first argument. This keeps the API,
# the Dramatiq workers, and the scheduler on identical code/deps.
ROLE="${1:-api}"

case "$ROLE" in
  api)
    echo "[entrypoint] starting API"
    exec gunicorn app.main:app \
      --worker-class uvicorn.workers.UvicornWorker \
      --workers "${WEB_CONCURRENCY:-4}" \
      --bind 0.0.0.0:8000 \
      --timeout 60
    ;;
  worker)
    echo "[entrypoint] starting Dramatiq worker"
    exec dramatiq app.worker --processes "${DRAMATIQ_PROCESSES:-2}" --threads "${DRAMATIQ_THREADS:-8}"
    ;;
  scheduler)
    echo "[entrypoint] starting scheduler"
    exec env KORE_ROLE=scheduler python -m app.worker
    ;;
  migrate)
    echo "[entrypoint] running migrations"
    exec alembic upgrade head
    ;;
  *)
    echo "[entrypoint] unknown role: $ROLE" >&2
    exit 1
    ;;
esac
