#!/usr/bin/env bash
# Version-header gate (ADR-206, plan 83 B): the STATUS phase header, the
# frontend package.json and any other [[propagate]] target must match
# backend/app/__init__.py::__version__. Fails CI when one drifts.
#
# Usage:
#   scripts/check-status-version.sh
#   scripts/check-status-version.sh --help
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi

exec python3 scripts/version_manager.py check
