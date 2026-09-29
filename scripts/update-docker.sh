#!/bin/bash

# Study Assistant — one-command Docker update.
#
# Updates an existing standalone Docker install (PostgreSQL 16 stack):
# git pull (best-effort) → pull (when STUDY_IMAGE points at a registry) /
# rebuild → up -d → wait for the app healthy.
#
# Usage:
#   ./scripts/update-docker.sh            # pull code + images, rebuild, restart
#   ./scripts/update-docker.sh --no-pull  # skip git pull and image pulls
#   ./scripts/update-docker.sh --no-wait  # skip the health-wait
#   ./scripts/update-docker.sh -h|--help  # print this help and exit
#
# Idempotent: never bricks a running install — a failed git pull is a warning,
# not an error, and docker/.env is never overwritten. Database and data
# volumes are untouched.

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

if [ "$NO_PULL" -eq 0 ]; then
    echo -e "${GREEN}Pulling latest code...${NC}"
    if git pull --ff-only; then
        echo -e "${GREEN}Code updated.${NC}"
    else
        echo -e "${YELLOW}git pull failed (dirty tree or offline?) — continuing with local code.${NC}"
    fi
fi

echo -e "${GREEN}Refreshing images and restarting the stack...${NC}"
if [ "$NO_PULL" -eq 0 ]; then
    refresh_images
fi
up_stack || die "docker compose up failed — see the output above (try: ${DOCKER_COMPOSE_CMD[*]} ${COMPOSE_ENV_ARGS[*]} logs app)"

if [ "$NO_WAIT" -eq 0 ]; then
    wait_for_backend_healthy || exit 1
fi

echo -e "${GREEN}Update complete.${NC}"
