#!/usr/bin/env bash
# Deprecated alias kept for muscle memory and old tooling: use scripts/run-dev.sh.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$DIR/run-dev.sh" "$@"
