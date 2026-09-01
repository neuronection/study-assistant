#!/bin/bash

# Study Assistant — shared helpers for the Docker ops scripts.
#
# Sourced by scripts/run-docker.sh and scripts/update-docker.sh; not meant
# to be run directly. Family-adapted from Health Assistant's lib-docker.sh.

# Colors for output
# shellcheck disable=SC2034  # YELLOW is used by the sourcing scripts
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

COMPOSE_FILE="docker/docker-compose.standalone.yml"
COMPOSE_ENV_ARGS=(--env-file .env -f "${COMPOSE_FILE}")
HEALTH_URL="http://127.0.0.1:${HTTP_PORT:-80}/api/v1/health"

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
    # Optional for study: the standalone stack has no required secrets
    # (SQLite, no admin bootstrap). A root .env is honored when present.
    if [ ! -f ".env" ]; then
        echo -e "${YELLOW}Note: no root .env — using built-in defaults (SA_DATA_DIR=/data volume).${NC}"
        COMPOSE_ENV_ARGS=(-f "${COMPOSE_FILE}")
    fi
}

# run_compose ARGS... — run docker compose with the standalone stack args.
run_compose() {
    # DOCKER_COMPOSE_CMD intentionally word-splits: "docker compose" or "docker-compose".
    # shellcheck disable=SC2086
    $DOCKER_COMPOSE_CMD "${COMPOSE_ENV_ARGS[@]}" "$@"
}

# Wait until the backend reports healthy via the nginx entrypoint.
wait_for_backend_healthy() {
    echo -e "${GREEN}Waiting for the backend to become healthy...${NC}"
    for _ in $(seq 1 60); do
        if curl -fsS "$HEALTH_URL" 2>/dev/null | grep -q '"status"'; then
            echo -e "${GREEN}Backend is healthy: ${HEALTH_URL}${NC}"
            return 0
        fi
        sleep 2
    done
    echo -e "${RED}Backend did not become healthy within 120s. Check: ${DOCKER_COMPOSE_CMD[*]} ${COMPOSE_ENV_ARGS[*]} logs backend${NC}" >&2
    return 1
}
