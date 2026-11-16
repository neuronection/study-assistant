#!/bin/sh
# Scheduled study backup: pg_dump + optional data tar, one JSONL ledger row
# per run (ADR-0063). Same-host by design; T1 off-host is a host timer
# running scripts/backup.sh (see docs/dev/backup-timer.md).
set -eu
INTERVAL="${BACKUP_INTERVAL_HOURS:-24}"
KEEP="${BACKUP_KEEP:-14}"

while :; do
  ts="$(date -u +%Y%m%d-%H%M%S)"
  dump="/backups/db-${ts}.dump"
  status="ok"; error=""
  pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > "$dump" || { status="failed"; error="pg_dump"; rm -f "$dump"; }
  data=""
  if [ "$status" = "ok" ] && [ "${SA_OBJECT_STORAGE_BACKEND:-local}" = "local" ] && [ -z "${SA_CLOUD_PROFILE:-}" ]; then
    data="/backups/data-${ts}.tar.gz"
    tar czf "$data" -C /data . || { status="failed"; error="data-tar"; rm -f "$data"; }
  fi
  bytes="$(stat -c%s "$dump" 2>/dev/null || echo 0)"
  sha="$(sha256sum "$dump" 2>/dev/null | awk '{print $1}')"
  printf '{"run_at":"%s","archive":"%s","bytes":%s,"sha256":"%s","uploaded_to":"local-only","status":"%s","error":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$dump" "$bytes" "$sha" "$status" "$error" >> /backups/backup_runs.jsonl
  find /backups -name 'db-*.dump' | sort | head -n -"$KEEP" | xargs -r rm --
  find /backups -name 'data-*.tar.gz' | sort | head -n -"$KEEP" | xargs -r rm --
  sleep "$((INTERVAL * 3600))"
done
