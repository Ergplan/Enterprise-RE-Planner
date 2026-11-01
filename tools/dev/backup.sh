#!/usr/bin/env bash
# Nightly backup of the server, the VM or the Mac mini (production compose only, not a laptop): a compressed pg_dump of the database and an archive of data/
# (documents, bill files, IEX files), kept for BACKUP_KEEP_DAYS (default 14) under BACKUP_DIR, and
# copied to a Cloud Storage bucket when BACKUP_BUCKET (gs://…) is set.
#   crontab: 30 2 * * * cd /opt/ergplan && tools/dev/backup.sh >> /var/log/ergplan-backup.log 2>&1
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIR="${BACKUP_DIR:-/var/backups/ergplan}"
KEEP="${BACKUP_KEEP_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
if [ -n "${BACKUP_BUCKET:-}" ] && ! command -v gsutil >/dev/null; then
  echo "backup: BACKUP_BUCKET is set but gsutil is not installed (install the Google Cloud CLI)" >&2
  exit 1
fi
mkdir -p "$DIR"
cd "$ROOT"
COMPOSE=(docker compose -f docker/compose.yaml -f docker/compose.prod.yaml)
[ -f .env ] && COMPOSE=(docker compose --env-file .env -f docker/compose.yaml -f docker/compose.prod.yaml)
# the Mac mini server (tools/dev/mini-install.sh schedules this with ERGPLAN_SERVER=mini)
[ "${ERGPLAN_SERVER:-}" = mini ] && COMPOSE+=(-f docker/compose.mini.yaml)
"${COMPOSE[@]}" exec -T postgres sh -c 'pg_dump -U "${POSTGRES_USER:-ergplan}" -Fc "${POSTGRES_DB:-ergplan}"' > "$DIR/db-$STAMP.dump"
# data/corpus is the copy of the source PDFs (registered copies live in data/documents)
tar -C "$ROOT" --exclude data/corpus -czf "$DIR/data-$STAMP.tar.gz" data
SHA=(sha256sum); command -v sha256sum >/dev/null || SHA=(shasum -a 256)  # macOS has shasum
"${SHA[@]}" "$DIR/db-$STAMP.dump" "$DIR/data-$STAMP.tar.gz" > "$DIR/$STAMP.sha256"
if [ -n "${BACKUP_BUCKET:-}" ]; then
  gsutil -q cp "$DIR/db-$STAMP.dump" "$DIR/data-$STAMP.tar.gz" "$DIR/$STAMP.sha256" "$BACKUP_BUCKET/$STAMP/"
fi
find "$DIR" -type f -mtime +"$KEEP" -delete
echo "backup $STAMP: $(du -sh "$DIR" | cut -f1) in $DIR"
