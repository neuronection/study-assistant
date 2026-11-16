#!/usr/bin/env bash
# Study Assistant instance backup (Docker deployment): Postgres dump + data
# volume (blobs, cache, thumbnails, import-inbox, in-app backups).
# Usage: scripts/backup.sh [output-dir]
# Reads docker/.env (or environment) for SA_DB_* settings. Output:
#   <output-dir>/study-assistant-YYYYMMDD-HHMMSS.tar.gz
#     manifest.json   — what this archive contains
#     database.dump   — pg_dump custom format (neuronection_study)
#     data.tar.gz     — the `data` volume (SA_DATA_DIR=/data)
#   <output-dir>/backup_runs.jsonl — one ledger row per run (ADR-0063)
#
# Off-host upload (ADR-0063: a T1 backup must leave the host). Set one or
# more targets in docker/.env or the environment; every configured target
# receives the archive:
#   SA_BACKUP_RCLONE_REMOTE   rclone remote, e.g. "myremote:study-backups"
#   SA_BACKUP_S3_URI          S3 prefix,        e.g. "s3://bucket/study" (aws cli)
#   SA_BACKUP_AZURE_URL       azcopy target,    e.g. "https://acct.blob.core.windows.net/cont/study?<sas>"
# A run with no target is recorded in the ledger as "local-only" — on a T1
# deployment that is a DR gap, not a success.
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
DB_PASSWORD="${SA_DB_OWNER_PASSWORD:-${SA_DB_PASSWORD:?Set SA_DB_OWNER_PASSWORD (env or docker/.env)}}"
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
ARCHIVE_NAME="$(basename "$ARCHIVE")"
tar czf "$ARCHIVE" -C "$WORK" .
SHA="$(sha256sum "$ARCHIVE" | cut -d' ' -f1)"
BYTES="$(stat -c%s "$ARCHIVE")"

# --- off-host upload (ADR-0063) -------------------------------------------
# Every configured target gets the archive; a failed upload is loud (the
# script exits non-zero) and the ledger row records the failure.
STATUS="local-only"
declare -a UPLOADED=()
if [[ -n "${SA_BACKUP_RCLONE_REMOTE:-}" ]]; then
  echo "==> Uploading to rclone remote '$SA_BACKUP_RCLONE_REMOTE'"
  rclone copy "$ARCHIVE" "$SA_BACKUP_RCLONE_REMOTE/" \
    && UPLOADED+=("rclone:$SA_BACKUP_RCLONE_REMOTE") \
    || { STATUS="upload-failed"; echo "    rclone upload FAILED (archive kept locally)" >&2; }
fi
if [[ -n "${SA_BACKUP_S3_URI:-}" ]]; then
  echo "==> Uploading to S3 '$SA_BACKUP_S3_URI'"
  aws s3 cp "$ARCHIVE" "$SA_BACKUP_S3_URI/$ARCHIVE_NAME" \
    && UPLOADED+=("$SA_BACKUP_S3_URI") \
    || { STATUS="upload-failed"; echo "    aws s3 upload FAILED (archive kept locally)" >&2; }
fi
if [[ -n "${SA_BACKUP_AZURE_URL:-}" ]]; then
  echo "==> Uploading with azcopy"
  azcopy copy "$ARCHIVE" "$SA_BACKUP_AZURE_URL/$ARCHIVE_NAME" \
    && UPLOADED+=("azcopy:$SA_BACKUP_AZURE_URL") \
    || { STATUS="upload-failed"; echo "    azcopy upload FAILED (archive kept locally)" >&2; }
fi
if [[ "$STATUS" == "local-only" && "${#UPLOADED[@]}" -gt 0 ]]; then
  STATUS="uploaded"
fi
if [[ "$STATUS" == "local-only" ]]; then
  echo "    (no off-host target configured — this run stays on this host;"
  echo "     set SA_BACKUP_RCLONE_REMOTE / SA_BACKUP_S3_URI / SA_BACKUP_AZURE_URL)"
fi

# --- run ledger (ADR-0063: one row per run) --------------------------------
LEDGER="$OUT_DIR/backup_runs.jsonl"
UPLOADED_JSON="["
first=1
for target in "${UPLOADED[@]:-}"; do
  [[ -n "$target" ]] || continue
  [[ "$first" -eq 1 ]] || UPLOADED_JSON+=","
  UPLOADED_JSON+="\"$target\""
  first=0
done
UPLOADED_JSON+="]"
printf '{"run_at":"%s","archive":"%s","bytes":%s,"sha256":"%s","uploaded_to":%s,"status":"%s"}\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$ARCHIVE_NAME" "$BYTES" "$SHA" \
  "$UPLOADED_JSON" "$STATUS" >> "$LEDGER"

echo "==> Done: $ARCHIVE"
echo "    Ledger row appended: $LEDGER"
echo "    Restore with: scripts/restore.sh $ARCHIVE --yes"
echo "    Retention is manual: keep at least the last N archives off-machine."
if [[ "$STATUS" == "upload-failed" ]]; then
  echo "==> One or more off-host uploads FAILED — see above (ADR-0063)." >&2
  exit 1
fi
