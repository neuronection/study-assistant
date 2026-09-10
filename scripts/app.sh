#!/usr/bin/env bash
# App mode: desktop shell (pywebview/WebKitGTK) over the built SPA.
# Usage: scripts/app.sh [--rebuild] [--reset [--yes] [--all]]
#   --rebuild  rebuild the frontend even if dist exists
#   --reset    wipe the local database and storage before starting (confirmation prompt; --yes to skip, --all to include backups)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

REBUILD=0
RESET=0
RESET_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --rebuild) REBUILD=1 ;;
    --reset) RESET=1 ;;
    -y|--yes) RESET_ARGS+=(--yes) ;;
    -a|--all) RESET_ARGS+=(--all) ;;
    *) echo "unknown option: $arg (expected --rebuild or --reset)"; exit 1 ;;
  esac
done

if [[ "$REBUILD" -eq 1 || ! -f frontend/dist/index.html ]]; then
  pnpm --filter frontend build
fi

if [[ "$RESET" -eq 1 ]]; then
  uv run --directory backend python -m studyassistant reset "${RESET_ARGS[@]}"
fi

exec uv run --directory backend python -m studyassistant
