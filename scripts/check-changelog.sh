#!/usr/bin/env bash
# Docs-sync gate (family discipline): user-visible code changes must touch
# CHANGELOG.md. Fails when the diff over user-visible surfaces (backend/app,
# frontend/src) does not include a CHANGELOG.md modification.
#
# Usage:
#   scripts/check-changelog.sh [base-ref]      # default: HEAD~1
#   scripts/check-changelog.sh --help
#
# In CI (pull_request): pass the merge base, e.g.
#   scripts/check-changelog.sh "origin/$GITHUB_BASE_REF"
# Direct pushes to main are checked against HEAD~1 — for merge commits pass
# an explicit base.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi

BASE="${1:-HEAD~1}"

if ! git rev-parse --verify --quiet "$BASE" >/dev/null; then
  echo "check-changelog: base ref '$BASE' not found — pass an explicit base." >&2
  exit 1
fi

changed="$(git diff --name-only "$BASE" -- backend/app frontend/src CHANGELOG.md)"
if [[ -z "$changed" ]]; then
  echo "check-changelog: no user-visible surfaces changed — OK"
  exit 0
fi

if grep -qx "CHANGELOG.md" <<<"$changed"; then
  echo "check-changelog: CHANGELOG.md updated alongside code — OK"
  exit 0
fi

echo "check-changelog: user-visible code changed without a CHANGELOG.md update." >&2
echo "  Changed surfaces:" >&2
grep -v '^CHANGELOG.md$' <<<"$changed" | sed 's/^/    /' >&2
echo "  Add an entry under ## [Unreleased] in CHANGELOG.md (family docs-sync" >&2
echo "  discipline), or document why no entry is needed in the PR description." >&2
exit 1
