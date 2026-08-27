#!/usr/bin/env bash
# Ежедневный бэкап PostgreSQL (через docker compose). Запускать по cron на VPS.
# Пример cron: 0 4 * * * /opt/delivery-bot/scripts/backup.sh >> /var/log/delivery-backup.log 2>&1
set -euo pipefail

cd "$(dirname "$0")/.."          # корень проекта (docker-compose.yml рядом)
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
FILE="$BACKUP_DIR/delivery_$STAMP.sql.gz"

# pg_dump внутри контейнера db, вывод пишем на host
docker compose exec -T db pg_dump -U delivery -d delivery | gzip > "$FILE"

# храним только последние N дней
find "$BACKUP_DIR" -name 'delivery_*.sql.gz' -mtime +"$RETENTION_DAYS" -delete

echo "OK: $FILE"