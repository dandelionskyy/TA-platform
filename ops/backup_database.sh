#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${ROOT_DIR:-/opt/ta-platform}"
BACKUP_DIR="${BACKUP_DIR:-/opt/backups/ta-platform}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
STAMP="$(date -u +%Y%m%d_%H%M%S)"

cd "$ROOT_DIR"
install -d -m 700 "$BACKUP_DIR"
tmp_db="$BACKUP_DIR/.ta_platform_${STAMP}.sql.gz.tmp"
tmp_uploads="$BACKUP_DIR/.uploads_${STAMP}.tar.gz.tmp"
trap 'rm -f "$tmp_db" "$tmp_uploads"' EXIT

docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip -9 > "$tmp_db"
docker run --rm \
  -v ta-platform_uploads:/data:ro \
  -v "$BACKUP_DIR":/backup \
  nginx:alpine sh -c "tar -czf /backup/$(basename "$tmp_uploads") -C /data ."

mv "$tmp_db" "$BACKUP_DIR/ta_platform_${STAMP}.sql.gz"
mv "$tmp_uploads" "$BACKUP_DIR/uploads_${STAMP}.tar.gz"
find "$BACKUP_DIR" -type f -name 'ta_platform_*.sql.gz' -mtime +"$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -type f -name 'uploads_*.tar.gz' -mtime +"$RETENTION_DAYS" -delete
echo "backup completed: $STAMP"
