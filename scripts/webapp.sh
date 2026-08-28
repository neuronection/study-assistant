#!/usr/bin/env bash
# Webapp mode: serve the built SPA from the backend and open it in the default browser.
# Usage: scripts/webapp.sh [--rebuild] [--force] [--reset [--yes] [--all]]
#   --rebuild  rebuild the frontend even if dist exists
#   --force    kill any process holding the port first
#   --reset    wipe the local database and storage before starting (confirmation prompt; --yes to skip, --all to include backups)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PORT="${SA_PORT:-8000}"
REBUILD=0
FORCE=0
RESET=0
RESET_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --rebuild) REBUILD=1 ;;
    -f|--force) FORCE=1 ;;
    --reset) RESET=1 ;;
    -y|--yes) RESET_ARGS+=(--yes) ;;
    -a|--all) RESET_ARGS+=(--all) ;;
    *) echo "unknown option: $arg (expected --rebuild, --force or --reset)"; exit 1 ;;
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

if [[ "$FORCE" -eq 1 || "$RESET" -eq 1 ]]; then
  pids="$(pids_on_port "$PORT")"
  for pid in $pids; do
    echo "killing pid $pid on port $PORT: $(describe_pid "$pid")"
    kill "$pid" 2>/dev/null || true
  done
  for _ in $(seq 1 20); do
    [[ -z "$(pids_on_port "$PORT")" ]] && break
    sleep 0.1
  done
  for pid in $(pids_on_port "$PORT"); do
    kill -9 "$pid" 2>/dev/null || true
  done
fi

if [[ "$RESET" -eq 1 ]]; then
  uv run --directory backend python -m studyassistant reset "${RESET_ARGS[@]}"
fi

if [[ "$REBUILD" -eq 1 || ! -f frontend/dist/index.html ]]; then
  pnpm --filter frontend build
fi

holders="$(pids_on_port "$PORT")"
if [[ -n "$holders" ]]; then
  echo "port $PORT is busy:"
  for pid in $holders; do
    echo "  pid $pid: $(describe_pid "$pid")"
  done
  echo "rerun with --force to kill it, or set SA_PORT to another port."
  exit 1
fi

exec env SA_PORT="$PORT" uv run --directory backend python -m studyassistant web
