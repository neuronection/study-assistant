#!/usr/bin/env bash
# Study Assistant — development entrypoint (uniform family interface).
#
# Starts backend (uvicorn --reload) + frontend (vite dev server) as one
# process group under honcho (Procfile.dev). A single Ctrl+C stops both; if
# either process dies honcho exits loud with the traceback in the foreground.
#
# Usage:
#   ./scripts/run-dev.sh                  # start the honcho group
#   ./scripts/run-dev.sh --force          # kill processes holding the ports first
#   ./scripts/run-dev.sh --force-stop     # stop all study dev processes, exit
#   ./scripts/run-dev.sh --reset [--yes] [--all]
#                                         # wipe the local database and storage
#                                         # before starting (confirmation prompt;
#                                         # --yes to skip it, --all to include backups)
#   ./scripts/run-dev.sh --no-bootstrap   # skip dep bootstrap, just start
#   ./scripts/run-dev.sh -h | --help      # print this help and exit
#
# Ports: SA_PORT (backend, default 8000) and VITE_PORT (frontend, default 5173).
# Desktop mode (pywebview) is a single process: scripts/app.sh (`pnpm app`).
# Built-SPA mode served by the backend: scripts/webapp.sh (`pnpm webapp`).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
cd "$SCRIPT_DIR/.."
# shellcheck source=lib/dev-common.sh
source scripts/lib/dev-common.sh

BACKEND_PORT="${SA_PORT:-8000}"
VITE_PORT="${VITE_PORT:-5173}"
export SA_PORT="$BACKEND_PORT" VITE_PORT="$VITE_PORT"

RESET=0
RESET_ARGS=()
NO_BOOTSTRAP=false
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --force-stop)
      dc_pkill "uvicorn app.main:create_app"
      dc_pkill "vite.*--port $VITE_PORT"
      dc_kill_port "$BACKEND_PORT"
      dc_kill_port "$VITE_PORT"
      dc_ok "All Study Assistant dev processes stopped."
      exit 0
      ;;
    --force)
      dc_kill_port "$BACKEND_PORT"
      dc_kill_port "$VITE_PORT"
      ;;
    --reset) RESET=1 ;;
    --yes) RESET_ARGS+=(--yes) ;;
    --all) RESET_ARGS+=(--all) ;;
    --no-bootstrap) NO_BOOTSTRAP=true ;;
    -h|--help) dc_help "$SCRIPT_PATH" ;;
    *) dc_die "unknown option: $1 (expected --force, --force-stop, --reset, --no-bootstrap or --help)" ;;
  esac
  shift
done

if [[ "$RESET" -eq 1 ]]; then
  dc_kill_port "$BACKEND_PORT"
  dc_kill_port "$VITE_PORT"
  uv run --directory backend python -m studyassistant reset "${RESET_ARGS[@]}"
fi

if [[ "$NO_BOOTSTRAP" = false ]]; then
  dc_ensure_node_deps . pnpm
fi

dc_check_port_free "$BACKEND_PORT" "backend"
dc_check_port_free "$VITE_PORT" "frontend"

dc_info "backend  → http://127.0.0.1:$BACKEND_PORT (api docs: /api/docs when SA_DEBUG=1)"
dc_info "frontend → http://localhost:$VITE_PORT"
dc_info "Press Ctrl+C to stop all services."
uv run honcho start -f Procfile.dev
