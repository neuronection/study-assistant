#!/usr/bin/env bash
# Study Assistant — development entrypoint (uniform family interface).
#
# Starts backend (uvicorn --reload) + frontend (vite dev server) as one
# process group under honcho (Procfile.dev). A single Ctrl+C stops both; if
# either process dies honcho exits loud with the traceback in the foreground.
#
# Usage:
#   ./scripts/run-dev.sh                  # desktop dev: SQLite profile +
#                                         # desktop identity (no login UI;
#                                         # ADR-0023)
#   ./scripts/run-dev.sh --force          # kill processes holding the ports first
#   ./scripts/run-dev.sh --force-stop     # stop all study dev processes, exit
#   ./scripts/run-dev.sh --reset [--yes] [--all]
#                                         # wipe the local database and storage
#                                         # before starting (confirmation prompt;
#                                         # --yes to skip it, --all to include backups)
#   ./scripts/run-dev.sh --no-bootstrap   # skip dep bootstrap, just start
#   ./scripts/run-dev.sh --web            # web/server mode (ADR-0022):
#                                         #   SA_IDENTITY_MODE=server + PostgreSQL
#                                         #   (docker/docker-compose.dev-db.yml,
#                                         #   neuronection_study @ 127.0.0.1:5434) — the SPA
#                                         #   shows the login/register UI
#   ./scripts/run-dev.sh -h | --help      # print this help and exit
#
# Ports (family dev-port bands, dev/guidelines/dev-ports.md): study is slot 2,
# so SA_PORT defaults to 8200 and VITE_PORT to 3200 (dev-db Postgres: 5434).
# Desktop mode (pywebview) is a single process: scripts/app.sh (`pnpm app`).
# Built-SPA mode served by the backend: scripts/webapp.sh (`pnpm webapp`).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
cd "$SCRIPT_DIR/.."
# shellcheck source=scripts/lib/dev-common.sh
source scripts/lib/dev-common.sh

BACKEND_PORT="${SA_PORT:-8200}"
VITE_PORT="${VITE_PORT:-3200}"
export SA_PORT="$BACKEND_PORT" VITE_PORT="$VITE_PORT"
# Dev boot: the family boot guards (nx_auth.boot) otherwise assume
# production (fail-safe default) and demand pinned keys on server boots.
export SA_APP_ENV="${SA_APP_ENV:-development}"

RESET=0
RESET_ARGS=()
NO_BOOTSTRAP=false
WEB=false
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
    --web) WEB=true ;;
    -h|--help) dc_help "$SCRIPT_PATH" ;;
    *) dc_die "unknown option: $1 (expected --force, --force-stop, --reset, --web, --no-bootstrap or --help)" ;;
  esac
  shift
done

if [[ "$RESET" -eq 1 ]]; then
  if [[ "$WEB" = true ]]; then
    dc_die "--reset is desktop-mode only; reset web mode with: docker compose --env-file .env -f docker/docker-compose.dev-db.yml down -v && up -d"
  fi
  dc_kill_port "$BACKEND_PORT"
  dc_kill_port "$VITE_PORT"
  uv run --directory backend python -m studyassistant reset "${RESET_ARGS[@]}"
fi

if [[ "$WEB" = true ]]; then
  # Web/server mode (ADR-0022): PostgreSQL 16 + authentication. The SPA
  # shows the login/register UI; first registered user becomes admin.
  export SA_IDENTITY_MODE=server
  : "${SA_DATABASE_URL:=postgresql+psycopg://neuronection_study_owner:neuronection_study_dev@127.0.0.1:5434/neuronection_study}"
  export SA_DATABASE_URL
  dc_info "web mode   → identity: server, database: ${SA_DATABASE_URL%%\?*}"
  if ! dc_port_in_use 5434; then
    if command -v docker >/dev/null 2>&1; then
      dc_info "dev-db not reachable on 5434 — starting docker/docker-compose.dev-db.yml"
      # --env-file: compose interpolates ${POSTGRES_DB}/${POSTGRES_TEST_DB}/
      # ${SA_DB_PORT} from the compose file's *directory* .env by default —
      # i.e. docker/.env, the standalone/prod stack's env file — so a prod
      # value could silently reshape the dev DB the run script then connects
      # to. Pin the interpolation to the dev root .env (empty env when it is
      # absent); shell exports (worktree-style SA_DB_PORT/
      # COMPOSE_PROJECT_NAME overrides) still win over it. The bootstrap
      # password is already pinned in the compose file for the same reason.
      dev_db_env=.env; [[ -f "$dev_db_env" ]] || dev_db_env=/dev/null
      docker compose --env-file "$dev_db_env" -f docker/docker-compose.dev-db.yml up -d
      dc_info "waiting for the dev-db to accept connections"
      ready=""
      for _ in $(seq 1 60); do
        if (exec 3<>/dev/tcp/127.0.0.1/5434) 2>/dev/null; then
          exec 3>&- 3<&- || true
          ready=1
          break
        fi
        sleep 1
      done
      [[ -n "$ready" ]] || dc_die "dev-db did not become ready on 5434"
    else
      dc_die "Postgres not reachable on 5434 and docker is unavailable — start a dev Postgres or set SA_DATABASE_URL"
    fi
  fi
else
  # Desktop dev (ADR-0023): local SQLite profile + desktop identity — no
  # login UI. Exported explicitly because the Settings default is
  # "server"; without this the "desktop" dev loop silently ran server
  # identity on SQLite.
  export SA_IDENTITY_MODE=desktop
  dc_info "desktop mode → identity: desktop, database: SQLite (local profile)"
fi

if [[ "$NO_BOOTSTRAP" = false ]]; then
  dc_ensure_node_deps . pnpm
fi

dc_check_port_free "$BACKEND_PORT" "backend"
dc_check_port_free "$VITE_PORT" "frontend"

# D6: migrations are an explicit dev step — `create_app` never migrates
# (plan 20 Phase 4). Desktop profile: local SQLite; --web: the dev
# Postgres on 5434.
dc_info "migrations  → alembic upgrade head"
(cd backend && uv run alembic upgrade head)

dc_info "backend  → http://127.0.0.1:$BACKEND_PORT (api docs: /api/docs when SA_DEBUG=1)"
dc_info "frontend → http://localhost:$VITE_PORT"
dc_info "Press Ctrl+C to stop all services."
uv run honcho start -f Procfile.dev
