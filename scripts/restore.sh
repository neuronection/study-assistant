#!/usr/bin/env bash
# Restore a Study Assistant instance backup produced by scripts/backup.sh.
# Usage: scripts/restore.sh <archive.tar.gz> [--yes]
#        FORCE=1 scripts/restore.sh <archive.tar.gz>
#
# WARNING: replaces the current database contents and the data volume.
# Nothing is touched without the explicit --yes flag (or FORCE=1).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARCHIVE=""
CONFIRM=0
for arg in "$@"; do
  case "$arg" in
    --yes|-y) CONFIRM=1 ;;
    -h|--help) awk 'FNR==1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "$0"; exit 0 ;;
    *) ARCHIVE="$arg" ;;
  esac
done
if [[ -z "$ARCHIVE" ]]; then
  echo "Usage: scripts/restore.sh <archive.tar.gz> [--yes]  (or FORCE=1)" >&2
  exit 1
fi
if [[ ! -f "$ARCHIVE" ]]; then
  echo "No such archive: $ARCHIVE" >&2
  exit 1
fi
if [[ "${FORCE:-0}" == "1" ]]; then
  CONFIRM=1
fi

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

DB_NAME="${SA_DB_NAME:-neuro_study}"
DB_OWNER="${SA_DB_OWNER:-neuro_study_owner}"
DB_PASSWORD="${SA_DB_PASSWORD:?Set SA_DB_PASSWORD (env or docker/.env)}"
PROJECT="${SA_COMPOSE_PROJECT:-study-assistant}"
COMPOSE_FILE="${SA_COMPOSE_FILE:-docker/docker-compose.standalone.yml}"
COMPOSE=(docker compose -f "$ROOT/$COMPOSE_FILE")

echo "==> This restore will DESTROY:"
echo "    - every object in the '$DB_NAME' database (volume ${PROJECT}_db_data),"
echo "      replaced from database.dump with pg_restore --clean --if-exists"
echo "    - all files in the '${PROJECT}_data' data volume (blobs, cache,"
echo "      thumbnails, import-inbox, in-app backups), replaced from data.tar.gz"
echo "    Archive: $ARCHIVE"
if [[ "$CONFIRM" -ne 1 ]]; then
  echo "==> Refusing to proceed without explicit confirmation." >&2
  echo "    Re-run with: scripts/restore.sh $ARCHIVE --yes   (or FORCE=1)" >&2
  exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
tar xzf "$ARCHIVE" -C "$WORK"

echo "==> Restoring database '$DB_NAME' (drops existing rows)"
"${COMPOSE[@]}" exec -T db \
  env PGPASSWORD="$DB_PASSWORD" pg_restore -U "$DB_OWNER" \
  -d "$DB_NAME" --clean --if-exists < "$WORK/database.dump"

echo "==> Restoring data volume"
docker run --rm -v "${PROJECT}_data":/data -v "$WORK":/in:ro alpine \
  sh -c "rm -rf /data/* && tar xzf /in/data.tar.gz -C /data"

echo "==> Done. Restart the app to re-run migrations if needed:"
echo "    ${COMPOSE[*]} up -d"
