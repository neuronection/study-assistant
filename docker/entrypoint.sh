#!/bin/sh
set -e

echo "Running database migrations..."
cd /app/backend
PYTHONPATH=/app/backend /app/.venv/bin/alembic upgrade head

echo "Starting Study Assistant (web mode) on ${SA_HOST:-0.0.0.0}:${SA_PORT:-8000}"
exec env PYTHONPATH=/app/backend \
    /app/.venv/bin/uvicorn app.main:create_app --factory \
    --host "${SA_HOST:-0.0.0.0}" --port "${SA_PORT:-8000}"
