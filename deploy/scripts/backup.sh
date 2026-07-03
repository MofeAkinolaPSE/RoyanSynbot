#!/bin/sh
# Royan Hospital — Daily PostgreSQL backup
# Runs at 02:00 via cron inside the backup container.
# Keeps 30 days of backups; older files are pruned automatically.

set -e

BACKUP_DIR="/backups"
DB_HOST="${POSTGRES_HOST:-db}"
DB_USER="${POSTGRES_USER:-royan}"
DB_NAME="${POSTGRES_DB:-royan_hospital}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILENAME="${BACKUP_DIR}/royan_${TIMESTAMP}.sql.gz"
KEEP_DAYS=30

echo "[$(date)] Starting backup → ${FILENAME}"

pg_dump -h "${DB_HOST}" -U "${DB_USER}" "${DB_NAME}" | gzip > "${FILENAME}"

echo "[$(date)] Backup complete: $(du -sh ${FILENAME} | cut -f1)"

# Prune backups older than KEEP_DAYS days
find "${BACKUP_DIR}" -name "royan_*.sql.gz" -mtime "+${KEEP_DAYS}" -delete
echo "[$(date)] Pruned backups older than ${KEEP_DAYS} days"

# Keep a latest symlink for easy restore
ln -sf "${FILENAME}" "${BACKUP_DIR}/latest.sql.gz"

echo "[$(date)] Done."
