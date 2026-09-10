#!/usr/bin/env bash
# Sync canonical brand assets to derived copies: assets/icon.svg is the single
# source of truth; frontend/public/icon.svg (Vite-served favicon) is derived.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cp "$ROOT/assets/icon.svg" "$ROOT/frontend/public/icon.svg"
echo "sync-brand: assets/icon.svg -> frontend/public/icon.svg"
