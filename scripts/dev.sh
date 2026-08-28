#!/usr/bin/env bash
# Dev mode: uvicorn (reload) + Vite dev server with /api and /ws proxying.
# Usage: scripts/dev.sh [--force] [--reset [--yes] [--all]]
#   --force  kill processes holding the ports first
#   --reset  wipe the local database and storage before starting (confirmation prompt; --yes to skip, --all to include backups)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

BACKEND_PORT="${SA_PORT:-8000}"
VITE_PORT="${VITE_PORT:-5173}"

FORCE=0
RESET=0
RESET_ARGS=()
for arg in "$@"; do
  case "$arg" in
    -f|--force) FORCE=1 ;;
    --reset) RESET=1 ;;
    -y|--yes) RESET_ARGS+=(--yes) ;;
    -a|--all) RESET_ARGS+=(--all) ;;
    *) echo "unknown option: $arg (expected --force or --reset)"; exit 1 ;;
  esac
done

pids_on_port() {
  local port="$1"
  if command -v fuser >/dev/null 2>&1; then
    fuser "${port}/tcp" 2>/dev/null || true
  else
    ss -tlnp 2>/dev/null | grep -E "[:.]${port}\s" | grep -oP 'pid=\K[0-9]+' | sort -u || true
  fi
}

describe_pid() {
  tr '\0' ' ' < "/proc/$1/cmdline" 2>/dev/null || echo "pid $1"
}

kill_port() {
  local port="$1" pids
  pids="$(pids_on_port "$port")"
  if [[ -n "$pids" ]]; then
    for pid in $pids; do
      echo "killing pid $pid on port $port: $(describe_pid "$pid")"
      kill "$pid" 2>/dev/null || true
    done
    for _ in $(seq 1 20); do
      [[ -z "$(pids_on_port "$port")" ]] && return 0
      sleep 0.1
    done
    for pid in $(pids_on_port "$port"); do
      kill -9 "$pid" 2>/dev/null || true
    done
  fi
}

if [[ "$FORCE" -eq 1 || "$RESET" -eq 1 ]]; then
  kill_port "$BACKEND_PORT"
  kill_port "$VITE_PORT"
fi

if [[ "$RESET" -eq 1 ]]; then
  uv run --directory backend python -m studyassistant reset "${RESET_ARGS[@]}"
fi

holders="$(pids_on_port "$BACKEND_PORT")"
if [[ -n "$holders" ]]; then
  echo "port $BACKEND_PORT is busy:"
  for pid in $holders; do
    echo "  pid $pid: $(describe_pid "$pid")"
  done
  echo "rerun with --force to kill it, or set SA_PORT to another port."
  exit 1
fi

trap 'kill 0' EXIT INT TERM

echo "backend  → http://127.0.0.1:$BACKEND_PORT (api docs: /api/docs when SA_DEBUG=1)"
echo "frontend → http://localhost:$VITE_PORT"

uv run --directory backend uvicorn app.main:create_app --factory --reload --port "$BACKEND_PORT" &
pnpm --filter frontend dev --port "$VITE_PORT" &
wait
