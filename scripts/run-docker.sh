#!/bin/bash

# Study Assistant — Docker deploy script (standalone self-hosted stack).
#
# First deploy of docker/docker-compose.standalone.yml (db + app + nginx;
# PostgreSQL 16, optional --profile backup sidecar): build (or pull, when
# STUDY_IMAGE points at a registry) → up -d → wait healthy → print the URL.
# To refresh an existing install use scripts/update-docker.sh.
#
# Usage:
#   ./scripts/run-docker.sh              # build/pull + up + wait for healthy
#   ./scripts/run-docker.sh --no-pull    # don't pull STUDY_IMAGE (build instead)
#   ./scripts/run-docker.sh --no-wait    # skip the health-wait
#   ./scripts/run-docker.sh -h|--help    # print this help and exit
#
# Run from the Study Assistant project root. Requires docker/.env
# (cp docker/.env.production.example docker/.env and set SA_DB_PASSWORD).

print_help() {
  awk 'FNR==1 { next }
       !started { if (/^#/) started=1; else next }
       /^#/ { sub(/^# ?/, ""); print; next }
       { exit }' "$0"
  exit 0
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib-docker.sh"

NO_PULL=0
NO_WAIT=0
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        -h|--help) print_help ;;
        --no-pull) NO_PULL=1 ;;
        --no-wait) NO_WAIT=1 ;;
        *) die "Unknown parameter: $1 (try --help)" ;;
    esac
    shift
done

check_cwd
check_docker
require_env

echo -e "${GREEN}Building and launching the Study Assistant stack...${NC}"
if [ "$NO_PULL" -eq 0 ]; then
    refresh_images
fi
up_stack || die "docker compose up failed — see the output above (try: ${DOCKER_COMPOSE_CMD[*]} ${COMPOSE_ENV_ARGS[*]} logs app)"

if [ "$NO_WAIT" -eq 0 ]; then
    wait_for_backend_healthy || exit 1
fi

echo -e "${GREEN}Study Assistant is up: ${APP_URL} (health: ${HEALTH_URL})${NC}"
