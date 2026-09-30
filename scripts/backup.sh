#!/usr/bin/env bash
# Study Assistant instance backup (Docker deployment): Postgres dump + data
# volume (blobs, cache, thumbnails, import-inbox, in-app backups).
# Usage: scripts/backup.sh [output-dir]
# Reads docker/.env (or environment) for SA_DB_* settings. Output:
#   <output-dir>/study-assistant-YYYYMMDD-HHMMSS.tar.gz
#     manifest.json   — what this archive contains
#     database.dump   — pg_dump custom format (neuronection_study)
#     data.tar.gz     — the `data` volume (SA_DATA_DIR=/data)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${1:-$ROOT/backups}"
mkdir -p "$OUT_DIR"

# Load docker/.env (family convention) or a root .env. Does not override
# real env vars.
for env_file in "$ROOT/docker/.env" "$ROOT/.env"; do
  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
    break
  fi
done

DB_NAME="${SA_DB_NAME:-neuronection_study}"
DB_OWNER="${SA_DB_OWNER:-neuronection_study_owner}"
DB_PASSWORD="${SA_DB_PASSWORD:?Set SA_DB_PASSWORD (env or docker/.env)}"
PROJECT="${SA_COMPOSE_PROJECT:-study-assistant}"
COMPOSE_FILE="${SA_COMPOSE_FILE:-docker/docker-compose.standalone.yml}"
COMPOSE=(docker compose -f "$ROOT/$COMPOSE_FILE")

STAMP="$(date -u +%Y%m%d-%H%M%S)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "==> Dumping database '$DB_NAME' (as $DB_OWNER)"
"${COMPOSE[@]}" exec -T db \
  env PGPASSWORD="$DB_PASSWORD" pg_dump -U "$DB_OWNER" -Fc "$DB_NAME" \
  > "$WORK/database.dump"

echo "==> Archiving data volume (blobs, cache, thumbnails, import-inbox)"
docker run --rm -v "${PROJECT}_data":/data:ro -v "$WORK":/out alpine \
  tar czf /out/data.tar.gz -C /data .

cat > "$WORK/manifest.json" <<EOF
{
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "contents": ["database.dump (pg_dump custom format)", "data.tar.gz (SA_DATA_DIR volume)"],
  "postgres_db": "$DB_NAME",
  "postgres_owner": "$DB_OWNER",
  "app_version": "see /api/v1/health"
}
EOF

ARCHIVE="$OUT_DIR/study-assistant-$STAMP.tar.gz"
tar czf "$ARCHIVE" -C "$WORK" .
echo "==> Done: $ARCHIVE"
echo "    Restore with: scripts/restore.sh $ARCHIVE --yes"
echo "    Retention is manual: keep at least the last N archives off-machine."
