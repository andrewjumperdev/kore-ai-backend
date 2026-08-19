#!/bin/sh
# Backup diario de Postgres con retención.
#
# Corre como un servicio propio en vez de un cron del host: así el backup viaja
# con el compose y no depende de que alguien lo configure a mano en cada VPS.
#
# El dump se escribe primero a un archivo temporal y recién al terminar se
# renombra: si el proceso muere a mitad de camino, no queda un .sql.gz truncado
# haciéndose pasar por un backup válido.
set -eu

BACKUP_DIR=/backups
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-86400}"

mkdir -p "$BACKUP_DIR"

while true; do
    STAMP="$(date +%F_%H%M)"
    TMP="$BACKUP_DIR/.kore_${STAMP}.sql.gz.partial"
    FINAL="$BACKUP_DIR/kore_${STAMP}.sql.gz"

    echo "[backup] iniciando $STAMP"
    if pg_dump -h db -U kore -d kore | gzip > "$TMP"; then
        mv "$TMP" "$FINAL"
        echo "[backup] ok → $FINAL ($(du -h "$FINAL" | cut -f1))"
        find "$BACKUP_DIR" -name 'kore_*.sql.gz' -mtime "+$RETENTION_DAYS" -delete
    else
        rm -f "$TMP"
        echo "[backup] FALLÓ en $STAMP" >&2
    fi

    sleep "$INTERVAL_SECONDS"
done
