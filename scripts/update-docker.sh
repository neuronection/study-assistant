#!/bin/bash

# Study Assistant — one-command Docker update.
#
# Updates an existing standalone Docker install: git pull (best-effort) →
# rebuild the image (or pull when STUDY_IMAGE points at a registry) → up -d →
# wait for the backend healthy.
#
# Usage:
#   ./scripts/update-docker.sh            # pull code, rebuild, restart
#   ./scripts/update-docker.sh --no-pull  # don't git pull (refresh images only)
#   ./scripts/update-docker.sh --no-wait  # skip the health-wait
#   ./scripts/update-docker.sh -h|--help  # print this help and exit
#
# Idempotent: never bricks a running install — a failed git pull is a warning,
# not an error. SQLite data lives in the `data` volume and is untouched.

print_help() {
  sed -n '3,12p' "$0" | sed 's/^# \{0,1\}//'
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
if [ -n "${STUDY_IMAGE:-}" ]; then
    run_compose pull
fi
run_compose up --build -d

if [ "$NO_WAIT" -eq 0 ]; then
    wait_for_backend_healthy || exit 1
fi

echo -e "${GREEN}Update complete.${NC}"
