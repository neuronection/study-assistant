#!/bin/bash

# Study Assistant — shared helpers for the Docker ops scripts.
#
# Sourced by scripts/run-docker.sh, scripts/update-docker.sh and the
# bundle installer/updater (scripts/install.sh, scripts/update.sh); not
# meant to be run directly. Family-adapted from Health Assistant's
# lib-docker.sh.

# Colors for output
# shellcheck disable=SC2034  # YELLOW is used by the sourcing scripts
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

COMPOSE_FILE="docker/docker-compose.standalone.yml"
COMPOSE_ENV_ARGS=(--env-file docker/.env -f "${COMPOSE_FILE}")
HEALTH_URL="http://127.0.0.1:${HTTP_PORT:-80}/api/v1/health"
APP_URL="http://127.0.0.1:${HTTP_PORT:-80}/"

die() {
    echo -e "${RED}Error: $1${NC}" >&2
    exit 1
}

check_cwd() {
    if [ ! -d "backend" ] || [ ! -d "frontend" ]; then
        die "Please run this script from the Study Assistant root directory"
    fi
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        die "Docker is not installed. Please install Docker first."
    fi
    if ! docker info &> /dev/null; then
        die "Docker daemon is not running. Please start Docker first."
    fi
    DOCKER_COMPOSE_CMD="docker compose"
    if ! docker compose version &> /dev/null; then
        if command -v docker-compose &> /dev/null; then
            DOCKER_COMPOSE_CMD="docker-compose"
        else
            die "Docker Compose is not installed (neither 'docker compose' nor 'docker-compose' is available)."
        fi
    fi
}

require_env() {
    # Web mode runs PostgreSQL 16 (ADR-0022/ADR-0064): SA_DB_OWNER_PASSWORD
    # + SA_DB_PASSWORD are required by the compose `:?` guards. Prefer
    # docker/.env (family convention), fall back to a root .env.
    if [ -f "docker/.env" ]; then
        COMPOSE_ENV_ARGS=(--env-file docker/.env -f "${COMPOSE_FILE}")
    elif [ -f ".env" ]; then
        echo -e "${YELLOW}Note: using root .env (docker/.env is the family convention).${NC}"
        COMPOSE_ENV_ARGS=(--env-file .env -f "${COMPOSE_FILE}")
    else
        die "docker/.env not found. Run: cp docker/.env.production.example docker/.env && set SA_DB_OWNER_PASSWORD + SA_DB_PASSWORD"
    fi
}

# ── env-file helpers (shared installer/updater helpers) ──────────────────────
# Used by the bundle installer/updater (scripts/install.sh, update.sh); the
# developer scripts keep require_env above. Written to survive
# `set -euo pipefail` in the sourcing script.
#
# Study keeps its docker/.env → root .env fallback (family convention first):
# docker/.env when it exists, root .env when only that does, docker/.env when
# neither does (the installer then creates it from the example). The installer
# never migrates a root .env silently — it uses it where it is.

ENV_FILE="docker/.env"

resolve_env_file() {
    if [ -f "docker/.env" ]; then
        ENV_FILE="docker/.env"
    elif [ -f ".env" ]; then
        ENV_FILE=".env"
        echo -e "${YELLOW}Note: using root .env (docker/.env is the family convention).${NC}"
    else
        ENV_FILE="docker/.env"
    fi
    COMPOSE_ENV_ARGS=(--env-file "$ENV_FILE" -f "${COMPOSE_FILE}")
}

# Read one KEY from the env file (last occurrence wins, compose's own rule).
# Usage: env_value KEY [default]
env_value() {
    local VALUE
    VALUE="$(grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
    printf '%s' "${VALUE:-$2}"
}

# Persist KEY=VALUE in the env file without disturbing anything else. Replaces
# every uncommented occurrence (a duplicate cannot shadow the new value),
# appends when absent, writes through a temp file so a failure cannot
# truncate the file. The caller is responsible for never clobbering a KEY the
# operator set by hand — the installer only writes pins/ports and freshly
# generated secrets.
# Usage: set_env_value KEY VALUE
set_env_value() {
    local KEY="$1" VALUE="$2" TMP
    [ -f "$ENV_FILE" ] || die "set_env_value: $ENV_FILE not found in $(pwd)"
    TMP="$(mktemp)"
    awk -v k="$KEY" -v v="$VALUE" '
        index($0, k "=") == 1 { print k "=" v; next }
        { print }
    ' "$ENV_FILE" > "$TMP" || { rm -f "$TMP"; die "Could not update ${KEY} in ${ENV_FILE}"; }
    if ! grep -qE "^${KEY}=" "$TMP"; then
        printf '%s=%s\n' "$KEY" "$VALUE" >> "$TMP"
    fi
    cat "$TMP" > "$ENV_FILE"
    rm -f "$TMP"
}

# One scalar field from a JSON file, dotted-path form ("images.app").
# Strings and numbers (the schema's healthPath/setupMode/defaultPort…);
# booleans and null read as empty. python3 when available, sed fallback for
# flat fields, empty when the file or key is missing — callers carry their
# own defaults. Used for the release manifest (./manifest.json) and the
# product config (./installer.json) that ship with the source-free bundle.
# Usage: json_field FILE KEY[.KEY…]
json_field() {
    local FILE="$1" KEYPATH="$2" OUT=""
    [ -f "$FILE" ] || { printf ''; return 0; }
    if command -v python3 &>/dev/null; then
        OUT="$(python3 -c '
import json, sys
try:
    node = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
for part in sys.argv[2].split("."):
    node = node.get(part) if isinstance(node, dict) else None
    if node is None:
        sys.exit(0)
if isinstance(node, (str, int, float)) and not isinstance(node, bool):
    print(node)
' "$FILE" "$KEYPATH" 2>/dev/null || true)"
    fi
    if [ -z "$OUT" ]; then
        OUT="$(sed -n "s/.*\"${KEYPATH##*.}\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$FILE" 2>/dev/null | head -n1)"
    fi
    if [ -z "$OUT" ]; then
        # numeric scalar fallback (defaultPort, minRamGb…)
        OUT="$(sed -n "s/.*\"${KEYPATH##*.}\"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p" "$FILE" 2>/dev/null | head -n1)"
    fi
    printf '%s' "$OUT"
}

# A flat JSON array of strings as space-separated words (installer.json's
# imageKeys — the closed vocabulary of manifest image slots). Empty when the
# file or key is missing; callers warn and fall back.
# Usage: json_keys FILE KEY
json_keys() {
    local FILE="$1" KEY="$2" OUT=""
    [ -f "$FILE" ] || { printf ''; return 0; }
    if command -v python3 &>/dev/null; then
        OUT="$(python3 -c '
import json, sys
try:
    node = json.load(open(sys.argv[1])).get(sys.argv[2])
except Exception:
    sys.exit(0)
if isinstance(node, list):
    print(" ".join(str(v) for v in node))
' "$FILE" "$KEY" 2>/dev/null || true)"
    fi
    if [ -z "$OUT" ]; then
        OUT="$(sed -n "s/.*\"$KEY\"[[:space:]]*:[[:space:]]*\[\([^]]*\)\].*/\1/p" "$FILE" 2>/dev/null \
            | tr -d '"' | tr ',' ' ')"
    fi
    printf '%s' "$OUT"
}

# The compose project name (the pinned top-level `name:` — fallback
# "study-assistant") — used to reason about named volumes and port owners.
resolve_compose_project() {
    local PROJECT
    PROJECT="$(run_compose config --format json 2>/dev/null \
        | python3 -c 'import sys,json; print(json.load(sys.stdin).get("name",""))' 2>/dev/null || true)"
    [ -z "$PROJECT" ] && PROJECT="study-assistant"
    printf '%s' "$PROJECT"
}

# run_compose ARGS... — run docker compose with the standalone stack args.
run_compose() {
    # DOCKER_COMPOSE_CMD intentionally word-splits: "docker compose" or "docker-compose".
    # shellcheck disable=SC2086
    $DOCKER_COMPOSE_CMD "${COMPOSE_ENV_ARGS[@]}" "$@"
}

# refresh_images — pull the registry image when STUDY_IMAGE points at one;
# a no-op for local builds (compose builds instead).
refresh_images() {
    if [ -n "${STUDY_IMAGE:-}" ]; then
        run_compose pull
    fi
}

# up_stack — bring the stack up: registry image → no local build; otherwise
# build the image from docker/Dockerfile.
up_stack() {
    if [ -n "${STUDY_IMAGE:-}" ]; then
        run_compose up -d --no-build
    else
        run_compose up --build -d
    fi
}

# One-time database/role rename for the ADR-0022 amendment (2026-09-30):
# legacy `neuro_study*` names → `neuronection_study*` (database
# neuronection_study (+ _test / _demo), roles neuronection_study_owner /
# neuronection_study_app). Existing volumes ignore POSTGRES_DB after first
# boot, so the db service is started first and the names are inspected
# inside it. PostgreSQL refuses to rename the session's own user, so the
# owner role is renamed through a throwaway superuser, and it refuses to
# rename a database other clients are connected to, so a pending rename
# stops the stack first (the caller brings it straight back up). No-op on
# fresh installs and on re-runs (nothing legacy left to rename); a
# connected bootstrap role is required, else we fail loud with the manual
# recipe (docker/README.md → "Renaming neuro_* → neuronection_*").
migrate_legacy_db_names() {
    local PAIR ROLE OLD_DB NEW_DB OLD_EXISTS NEW_EXISTS CONNECTED="" PENDING=""
    local -a PSQL
    run_compose up -d db >/dev/null \
        || die "Could not start postgres to check legacy database names."
    for _ in $(seq 1 30); do
        for ROLE in neuronection_study_owner neuro_study_owner admin; do
            if run_compose exec -T db psql -U "$ROLE" -d postgres -tAc "select 1" >/dev/null 2>&1; then
                CONNECTED="$ROLE"
                break 2
            fi
        done
        sleep 2
    done
    [ -z "$CONNECTED" ] && die "Cannot connect to postgres to check legacy database names — see docker/README.md → \"Renaming neuro_* → neuronection_*\"."
    PSQL=(exec -T db psql -U "$CONNECTED" -d postgres -v ON_ERROR_STOP=1)

    # Inspect before mutating: rename only when the legacy name exists and
    # the new one is absent — a stack that already carries both is a manual
    # call — and remember that something is pending, because ALTER DATABASE
    # cannot run while clients hold a connection to the old database.
    for PAIR in \
        "neuro_study:neuronection_study" \
        "neuro_study_test:neuronection_study_test" \
        "neuro_study_demo:neuronection_study_demo"; do
        OLD_DB="${PAIR%%:*}"
        NEW_DB="${PAIR##*:}"
        OLD_EXISTS="$(run_compose "${PSQL[@]}" -tAc "select 1 from pg_database where datname='$OLD_DB'")"
        [ "$OLD_EXISTS" = "1" ] || continue
        NEW_EXISTS="$(run_compose "${PSQL[@]}" -tAc "select 1 from pg_database where datname='$NEW_DB'")"
        [ "$NEW_EXISTS" = "1" ] && die "Both ${OLD_DB} and ${NEW_DB} exist — resolve manually (dump the old one, restore into ${NEW_DB}) before re-running."
        PENDING=1
    done
    if [ "$(run_compose "${PSQL[@]}" -tAc "select 1 from pg_roles where rolname='neuro_study_app'")" = "1" ]; then
        [ "$(run_compose "${PSQL[@]}" -tAc "select 1 from pg_roles where rolname='neuronection_study_app'")" = "1" ] \
            && die "Both neuro_study_app and neuronection_study_app exist — resolve manually before re-running."
        PENDING=1
    fi
    if [ "$(run_compose "${PSQL[@]}" -tAc "select 1 from pg_roles where rolname='neuro_study_owner'")" = "1" ]; then
        [ "$(run_compose "${PSQL[@]}" -tAc "select 1 from pg_roles where rolname='neuronection_study_owner'")" = "1" ] \
            && die "Both neuro_study_owner and neuronection_study_owner exist — resolve manually before re-running."
        PENDING=1
    fi

    if [ -n "$PENDING" ]; then
        run_compose stop >/dev/null 2>&1 || true
        run_compose up -d db >/dev/null \
            || die "Could not restart postgres for the legacy rename."
        for _ in $(seq 1 30); do
            run_compose exec -T db psql -U "$CONNECTED" -d postgres -tAc "select 1" >/dev/null 2>&1 && break
            sleep 2
        done
        run_compose exec -T db psql -U "$CONNECTED" -d postgres -tAc "select 1" >/dev/null 2>&1 \
            || die "postgres did not come back for the legacy rename — see docker/README.md → \"Renaming neuro_* → neuronection_*\"."
    fi

    for PAIR in \
        "neuro_study:neuronection_study" \
        "neuro_study_test:neuronection_study_test" \
        "neuro_study_demo:neuronection_study_demo"; do
        OLD_DB="${PAIR%%:*}"
        NEW_DB="${PAIR##*:}"
        OLD_EXISTS="$(run_compose "${PSQL[@]}" -tAc "select 1 from pg_database where datname='$OLD_DB'")"
        [ "$OLD_EXISTS" = "1" ] || continue
        run_compose "${PSQL[@]}" -c "ALTER DATABASE \"${OLD_DB}\" RENAME TO \"${NEW_DB}\";" >/dev/null \
            || die "Could not rename database ${OLD_DB} → ${NEW_DB} — see docker/README.md → \"Renaming neuro_* → neuronection_*\"."
        echo -e "${GREEN}Renamed database ${OLD_DB} → ${NEW_DB}${NC}"
    done

    if [ "$(run_compose "${PSQL[@]}" -tAc "select 1 from pg_roles where rolname='neuro_study_app'")" = "1" ]; then
        run_compose "${PSQL[@]}" -c "ALTER ROLE neuro_study_app RENAME TO neuronection_study_app;" >/dev/null \
            || die "Could not rename role neuro_study_app — see docker/README.md → \"Renaming neuro_* → neuronection_*\"."
        echo -e "${GREEN}Renamed role neuro_study_app → neuronection_study_app${NC}"
    fi

    # The owner role goes last: once renamed, the bootstrap session user we
    # connected as may no longer exist.
    if [ "$(run_compose "${PSQL[@]}" -tAc "select 1 from pg_roles where rolname='neuro_study_owner'")" = "1" ]; then
        run_compose "${PSQL[@]}" -c "DROP ROLE IF EXISTS sa_db_migrator;" >/dev/null
        run_compose "${PSQL[@]}" -c "CREATE ROLE sa_db_migrator LOGIN SUPERUSER;" >/dev/null \
            || die "Could not create the throwaway sa_db_migrator role — see docker/README.md → \"Renaming neuro_* → neuronection_*\"."
        run_compose exec -T db \
            psql -U sa_db_migrator -d postgres -v ON_ERROR_STOP=1 \
            -c "ALTER ROLE neuro_study_owner RENAME TO neuronection_study_owner;" >/dev/null \
            || die "Could not rename role neuro_study_owner — see docker/README.md → \"Renaming neuro_* → neuronection_*\"."
        run_compose exec -T db \
            psql -U neuronection_study_owner -d postgres -v ON_ERROR_STOP=1 \
            -c "DROP ROLE sa_db_migrator;" >/dev/null
        echo -e "${GREEN}Renamed role neuro_study_owner → neuronection_study_owner${NC}"
    fi
    run_compose "${PSQL[@]}" -c "DROP ROLE IF EXISTS sa_db_migrator;" >/dev/null 2>&1 || true
}

# Wait until the app reports healthy via the nginx entrypoint. The poll
# interval and attempt count are overridable (HEALTH_WAIT_INTERVAL /
# HEALTH_WAIT_ATTEMPTS — the installer selftest drives both). On failure,
# name the compose services and the last log lines instead of pointing at
# a bare curl.
wait_for_backend_healthy() {
    local interval="${HEALTH_WAIT_INTERVAL:-2}"
    local attempts="${HEALTH_WAIT_ATTEMPTS:-60}"
    local i
    echo -e "${GREEN}Waiting for the app to become healthy at ${HEALTH_URL}...${NC}"
    for i in $(seq 1 "$attempts"); do
        if curl -fsS "$HEALTH_URL" 2>/dev/null | grep -q '"status"'; then
            echo -e "${GREEN}App is healthy: ${HEALTH_URL}${NC}"
            return 0
        fi
        sleep "$interval"
    done
    echo -e "${RED}App did not become healthy within $((attempts * interval))s.${NC}" >&2
    report_compose_failure
    return 1
}

# Print what the stack actually looks like plus the last log lines of the
# one-shot migrate job and the app, so a failed boot names its culprit
# instead of pointing at a bare health URL.
report_compose_failure() {
    echo -e "${YELLOW}Compose services:${NC}" >&2
    run_compose ps -a 2>/dev/null | sed 's/^/  /' >&2 || true
    echo -e "${YELLOW}Last log lines — migrate:${NC}" >&2
    run_compose logs --tail 15 migrate 2>/dev/null | sed 's/^/  /' >&2 || true
    echo -e "${YELLOW}Last log lines — app:${NC}" >&2
    run_compose logs --tail 15 app 2>/dev/null | sed 's/^/  /' >&2 || true
    echo >&2
    echo -e "Fix the failure above, then re-run this script — it reuses ${ENV_FILE}." >&2
    echo -e "Dig deeper: ${DOCKER_COMPOSE_CMD[*]} ${COMPOSE_ENV_ARGS[*]} logs migrate" >&2
}

# ── Published-port pre-flight ────────────────────────────────────────────────
# A bind conflict otherwise surfaces mid-startup as a raw daemon error,
# after the pull, with no hint which knob to turn. The port set is read
# from the RENDERED compose model — the only source that knows about bind
# addresses and services added later — so this runs after the env file
# exists (compose interpolates it).

# Ports the stack would publish, as "<service>\t<port>" lines. Empty when
# the model cannot be rendered (no python3, compose v1, broken
# interpolation) — callers treat empty as "skip".
rendered_ports() {
    run_compose config --format json 2>/dev/null | python3 -c '
import json, sys
try:
    model = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for name, svc in (model.get("services") or {}).items():
    for spec in svc.get("ports") or []:
        published = spec.get("published")
        if not published:
            continue
        # compose may render "<ip>:<port>" (bind address) or "<port>";
        # a range "a-b" publishes every port in it.
        for port in str(published).split(":")[-1].split("-"):
            if port:
                print("%s\t%s" % (name, port))
' 2>/dev/null || true
}

# True when something accepts IPv4 connections on this host port. Loopback
# is where the standalone stack binds and also covers 0.0.0.0.
port_in_use() {
    python3 - "$1" <<'PY'
import socket, sys
sock = socket.socket()
sock.settimeout(0.3)
try:
    sock.connect(("127.0.0.1", int(sys.argv[1])))
except OSError:
    sys.exit(1)
finally:
    sock.close()
sys.exit(0)
PY
}

# True when every container publishing this port belongs to OUR compose
# project — the normal re-run case, which must not read as a conflict.
port_owner_is_project() {
    local PROJECTS
    PROJECTS="$(docker ps --filter "publish=$1" \
        --format '{{.Label "com.docker.compose.project"}}' 2>/dev/null \
        | sed '/^$/d' | sort -u || true)"
    [ -n "$PROJECTS" ] && [ "$PROJECTS" = "$2" ]
}

# The env-file variable a published port comes from. Matched by VALUE —
# the variable's current .env value, else its compose default — because the
# rendered port is the overridden one ("${HTTP_PORT:-80}" publishes 8091
# when the env file says 8091). Empty for literals ("80:80"), which can
# only be changed in the compose file itself.
port_env_var() {
    local PORT="$1" VAR VALUE DEFAULT
    # shellcheck disable=SC2013  # word-split list of compose env names is intended
    for VAR in $(grep -oE '\$\{[A-Z][A-Z0-9_]*(:-[0-9]+)?\}' "$COMPOSE_FILE" 2>/dev/null \
        | sed -E 's/^\$\{([A-Z][A-Z0-9_]*).*/\1/' | sort -u); do
        VALUE="$(env_value "$VAR" "")"
        if [ -n "$VALUE" ] && [ "$VALUE" = "$PORT" ]; then
            printf '%s' "$VAR"
            return 0
        fi
        if [ -z "$VALUE" ]; then
            DEFAULT="$(sed -n "s/.*\${${VAR}:-\([0-9][0-9]*\)}.*/\1/p" "$COMPOSE_FILE" | head -n1)"
            if [ "$DEFAULT" = "$PORT" ]; then
                printf '%s' "$VAR"
                return 0
            fi
        fi
    done
    return 1
}

next_free_port() {
    local PORT="$1" TRIES=0
    while [ "$TRIES" -lt 50 ] && [ "$PORT" -lt 65535 ]; do
        PORT=$((PORT + 1))
        port_in_use "$PORT" || { printf '%s' "$PORT"; return 0; }
        TRIES=$((TRIES + 1))
    done
    return 1
}

# Fail fast, before anything is pulled or started, when a published host
# port is already taken by something that is not this stack. --auto moves
# a busy port to the next free one and writes it to the env file instead.
# Exit code 4 = port conflict (the installer contract).
# Usage: check_published_ports [--auto]
check_published_ports() {
    local AUTO=0
    if [ "${1:-}" = "--auto" ]; then AUTO=1; fi
    local PROJECT LIST SVC PORT VAR FREE CONFLICTS=""
    PROJECT="$(resolve_compose_project)"
    LIST="$(rendered_ports)"
    if [ -z "$LIST" ]; then
        echo -e "${YELLOW}Port pre-flight: could not render the compose model — skipping.${NC}"
        return 0
    fi
    while IFS=$'\t' read -r SVC PORT; do
        [ -n "$PORT" ] || continue
        port_in_use "$PORT" || continue
        port_owner_is_project "$PORT" "$PROJECT" && continue
        VAR="$(port_env_var "$PORT" || true)"
        if [ "$AUTO" = "1" ] && [ -n "$VAR" ]; then
            FREE="$(next_free_port "$PORT")" || FREE=""
            if [ -n "$FREE" ]; then
                set_env_value "$VAR" "$FREE"
                echo -e "${GREEN}Port ${PORT} was busy — ${VAR}=${FREE} written to .env (${ENV_FILE}).${NC}"
                continue
            fi
        fi
        if [ -n "$VAR" ]; then
            CONFLICTS="${CONFLICTS}  ${SVC}: host port ${PORT} is in use → set ${VAR}=<free port> in ${ENV_FILE}"$'\n'
        else
            CONFLICTS="${CONFLICTS}  ${SVC}: host port ${PORT} is in use and is a literal in ${COMPOSE_FILE} → edit it there"$'\n'
        fi
    done <<< "$LIST"
    if [ -n "$CONFLICTS" ]; then
        echo -e "${RED}"
        echo "Port conflict — the stack cannot start:"
        printf '%s' "$CONFLICTS"
        echo -e "${NC}"
        echo "  Find the holder:  ss -ltnp | grep ':<port>'   (or: lsof -i :<port>)"
        echo "  Then re-run this script — it reuses ${ENV_FILE}."
        echo "  Or let the installer pick free ports: --auto-ports"
        echo -e "${RED}Aborted before pulling or starting anything.${NC}"
        exit 4
    fi
    echo -e "${GREEN}Port pre-flight: no conflicts.${NC}"
}
