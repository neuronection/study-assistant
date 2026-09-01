#!/bin/bash

# Study Assistant — Docker deploy script (standalone self-hosted stack).
#
# Builds the backend image and brings up docker/docker-compose.standalone.yml
# (backend + nginx; SQLite data volume). This is the first-time deploy; to
# refresh an existing install use scripts/update-docker.sh.
#
# Usage:
#   ./scripts/run-docker.sh              # build + up + wait for healthy
#   ./scripts/run-docker.sh -h|--help    # print this help and exit
#
# Run from the Study Assistant project root. A root .env is honored when
# present but not required (no secrets: SQLite + local-first data).

print_help() {
  sed -n '3,11p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib-docker.sh"

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        -h|--help) print_help ;;
        *) die "Unknown parameter: $1 (try --help)" ;;
    esac
done

check_cwd
check_docker
require_env

echo -e "${GREEN}Building and launching the Study Assistant stack...${NC}"
run_compose up --build -d

wait_for_backend_healthy || exit 1

echo -e "${GREEN}Study Assistant is up: ${HEALTH_URL}${NC}"
