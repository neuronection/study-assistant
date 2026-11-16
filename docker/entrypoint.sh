#!/bin/sh
set -e

# Modes (plan 20 Phase 4, D6 — migrations are an entrypoint/ops
# responsibility, never `create_app`'s; ADR-0062 v7 §3 / ADR-0064):
#   entrypoint.sh migrate   one-shot: wait for the DB, resolve the
#                           SA_DB_SPLIT tri-state (split/unsplit/broken),
#                           provision roles+extensions as the owner, apply
#                           migrations, checkpoint schema
#   entrypoint.sh serve     (default) boot the API — app DSN only, never the
#                           owner DSN, never DDL
# Compose runs `migrate` as a one-shot service and makes `app` depend on
# its successful completion.

# Demo guard (deployment.md): this image is the production deployment —
# abort on demo configuration. The demo flavor (docker-compose.demo.yml, S8)
# runs its own isolated stack and must set SA_APP_ENV=demo explicitly.
case "${SA_DEMO_MODE:-0}" in
    1|true|TRUE|True)
        if [ "${SA_APP_ENV:-production}" != "demo" ]; then
            echo "SA_DEMO_MODE=true is demo configuration — refusing to start a production deployment (deployment.md demo guards)." >&2
            exit 1
        fi
        ;;
esac

wait_for_db() {
    echo "Waiting for the database..."
    python -c '
import os, socket, sys, time
from urllib.parse import urlparse
raw = os.environ.get("SA_MIGRATIONS_DATABASE_URL") or os.environ.get("SA_DATABASE_URL") or ""
u = urlparse(raw)
host = u.hostname or os.environ.get("SA_DB_HOST", "localhost")
port = u.port or int(os.environ.get("SA_DB_PORT", "5432") or 5432)
deadline = time.monotonic() + 60
while time.monotonic() < deadline:
    try:
        socket.create_connection((host, port), timeout=2).close()
        sys.exit(0)
    except OSError:
        time.sleep(1)
sys.exit(f"database not reachable at {host}:{port}")
'
}

# app/ops/migrations (ADR-0062 v7 §3, ADR-0064): tri-state resolution
# (split / unsplit warning / broken refusal), owner-side provisioning
# (app role + grants + default privileges + vector/pg_trgm), Alembic as the
# owner role, the checkpoint schema, re-grant. The serving process never
# runs any of it.
run_migrations() {
    echo "Running database migrations (owner role, app/ops/migrations)..."
    PYTHONPATH=/app/backend /app/.venv/bin/python -m app.ops.migrations
}

case "${1:-serve}" in
    migrate)
        wait_for_db
        run_migrations
        ;;
    serve)
        # Owner DSN fail-closed (ADR-0064 §1/§4): a serving process never
        # holds the owner/migrations credential — it would silently regain
        # DDL rights. The compose files never inject it; an operator who
        # does gets a refusal instead of a running leak.
        if [ -n "${SA_MIGRATIONS_DATABASE_URL:-}" ]; then
            echo "REFUSING to serve: SA_MIGRATIONS_DATABASE_URL must not be set in the serving env (ADR-0064 — the owner DSN belongs to the one-shot migrate service only)." >&2
            exit 1
        fi
        echo "Starting Study Assistant (web mode) on ${SA_HOST:-0.0.0.0}:${SA_PORT:-8000}"
        exec env PYTHONPATH=/app/backend \
            /app/.venv/bin/uvicorn app.main:create_app --factory \
            --host "${SA_HOST:-0.0.0.0}" --port "${SA_PORT:-8000}"
        ;;
    *)
        exec "$@"
        ;;
esac
