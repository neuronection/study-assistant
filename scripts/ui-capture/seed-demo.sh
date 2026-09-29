#!/usr/bin/env bash
# Seed the Study Assistant demo workspace used for UI capture.
# Idempotent: initializes the demo DB on first run (empty target only),
# plain reseed afterwards. The seeder itself refuses any target that is
# not a demo instance — see scripts/seed-demo.py for the guard details.
#
# Also provisions the demo scripted tutor: the local mock AI provider
# (frontend/e2e/mock_provider.py) so tutor chat produces deterministic
# rich demo answers without any API key (seed-demo-ai.py), and starts it
# if it is not already listening.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEMO_DIR="${SA_DEMO_DIR:-$ROOT/dev/demo-data}"
MOCK_PORT="${SA_MOCK_PORT:-8321}"

if [[ ! -f "$DEMO_DIR/study.sqlite3" ]]; then
  uv run --directory "$ROOT/backend" python "$ROOT/scripts/seed-demo.py" --demo-dir "$DEMO_DIR" --init-demo
else
  uv run --directory "$ROOT/backend" python "$ROOT/scripts/seed-demo.py" --demo-dir "$DEMO_DIR"
fi

# Demo AI: provider rows in the demo DB + the scripted mock server.
uv run --directory "$ROOT/backend" python "$ROOT/scripts/ui-capture/seed-demo-ai.py" \
  --demo-dir "$DEMO_DIR" --base-url "http://127.0.0.1:${MOCK_PORT}/v1"

if ! curl -fsS -m 2 "http://127.0.0.1:${MOCK_PORT}/v1/models" >/dev/null 2>&1; then
  echo "→ Starting the demo scripted tutor on :${MOCK_PORT}…"
  PYTHONPATH="$ROOT/frontend/e2e" nohup uv run --directory "$ROOT/backend" python -m uvicorn mock_provider:app \
    --host 127.0.0.1 --port "$MOCK_PORT" \
    >>"$DEMO_DIR/mock-provider.log" 2>&1 &
  for _ in $(seq 1 30); do
    curl -fsS -m 2 "http://127.0.0.1:${MOCK_PORT}/v1/models" >/dev/null 2>&1 && break
    sleep 0.5
  done
fi
curl -fsS -m 2 "http://127.0.0.1:${MOCK_PORT}/v1/models" >/dev/null 2>&1 \
  || { echo "❌ demo scripted tutor not reachable on :${MOCK_PORT}"; exit 1; }
echo "✅ demo workspace + scripted tutor ready"
