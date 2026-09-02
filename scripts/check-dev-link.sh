#!/usr/bin/env bash
# Family-unified guard: fails when an assistant-ui dev-link override is
# present in a tracked manifest — `link:` in pnpm-workspace.yaml (pnpm)
# or a `file:`/`link:` dependency in any package.json (npm). The
# dev-link contract is "never commit manifest edits" (library
# docs/local-development.md); a committed link breaks CI installs
# because ../assistant-ui does not exist in the CI checkout.
#
# Runs as a pre-commit hook (scripts/githooks/) and as a CI step.
# Manual: scripts/check-dev-link.sh

set -uo pipefail
cd "$(dirname "$0")/.."

hits=0
for f in pnpm-workspace.yaml package.json frontend/package.json; do
  [ -f "$f" ] || continue
  if grep -nEq '(link:|file:)[^"]*assistant-ui' "$f"; then
    echo "✗ dev-link active in $f — never commit manifest edits." >&2
    echo "  Fix: node ../assistant-ui/scripts/dev-link.mjs unlink frontend  (then reinstall)" >&2
    hits=1
  fi
done

if [ "$hits" -eq 0 ]; then
  echo "✓ no assistant-ui dev-link in tracked manifests"
fi
exit "$hits"
