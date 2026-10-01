#!/bin/sh
set -e

# Modes (plan 20 Phase 4, D6 — migrations are an entrypoint/ops
# responsibility, never `create_app`'s):
#   entrypoint.sh migrate   one-shot: wait for the DB, apply migrations
#                           (owner role), provision the checkpoint schema
#   entrypoint.sh serve     (default) boot the API
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

run_migrations() {
    echo "Running database migrations (owner role)..."
    cd /app/backend
    if [ -n "${SA_MIGRATIONS_DATABASE_URL:-}" ]; then
        # Two-role split (deployment.md): migrations run as the owner role, the
        # app process connects as the least-privilege app role (SA_DATABASE_URL).
        SA_DATABASE_URL="$SA_MIGRATIONS_DATABASE_URL" PYTHONPATH=/app/backend \
            /app/.venv/bin/alembic upgrade head
        # langgraph's checkpoint schema is DDL too — provision it as the owner
        # role; the app's checkpointer tolerates its existence at boot.
        CHECKPOINT_URI="${SA_MIGRATIONS_DATABASE_URL/+psycopg/}" PYTHONPATH=/app/backend \
            /app/.venv/bin/python -c '
import asyncio, os
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def main() -> None:
    async with AsyncPostgresSaver.from_conn_string(os.environ["CHECKPOINT_URI"]) as saver:
        await saver.setup()

asyncio.run(main())
'
    else
        PYTHONPATH=/app/backend /app/.venv/bin/alembic upgrade head
    fi
}

case "${1:-serve}" in
    migrate)
        wait_for_db
        run_migrations
        ;;
    serve)
        echo "Starting Study Assistant (web mode) on ${SA_HOST:-0.0.0.0}:${SA_PORT:-8000}"
        exec env PYTHONPATH=/app/backend \
            /app/.venv/bin/uvicorn app.main:create_app --factory \
            --host "${SA_HOST:-0.0.0.0}" --port "${SA_PORT:-8000}"
        ;;
    *)
        exec "$@"
        ;;
esac
