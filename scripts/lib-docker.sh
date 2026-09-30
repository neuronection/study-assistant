#!/bin/bash

# Study Assistant — shared helpers for the Docker ops scripts.
#
# Sourced by scripts/run-docker.sh, scripts/update-docker.sh,
# scripts/backup.sh-style tooling; not meant to be run directly.
# Family-adapted from Health Assistant's lib-docker.sh.

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
    # Web mode runs PostgreSQL 16 (ADR-0022): SA_DB_PASSWORD is required by
    # the compose `:?` guards. Prefer docker/.env (family convention), fall
    # back to a root .env.
    if [ -f "docker/.env" ]; then
        COMPOSE_ENV_ARGS=(--env-file docker/.env -f "${COMPOSE_FILE}")
    elif [ -f ".env" ]; then
        echo -e "${YELLOW}Note: using root .env (docker/.env is the family convention).${NC}"
        COMPOSE_ENV_ARGS=(--env-file .env -f "${COMPOSE_FILE}")
    else
        die "docker/.env not found. Run: cp docker/.env.production.example docker/.env && set SA_DB_PASSWORD"
    fi
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

# Wait until the app reports healthy via the nginx entrypoint.
wait_for_backend_healthy() {
    echo -e "${GREEN}Waiting for the app to become healthy...${NC}"
    for _ in $(seq 1 60); do
        if curl -fsS "$HEALTH_URL" 2>/dev/null | grep -q '"status"'; then
            echo -e "${GREEN}App is healthy: ${HEALTH_URL}${NC}"
            return 0
        fi
        sleep 2
    done
    echo -e "${RED}App did not become healthy within 120s. Check: ${DOCKER_COMPOSE_CMD[*]} ${COMPOSE_ENV_ARGS[*]} logs app${NC}" >&2
    return 1
}
