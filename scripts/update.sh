#!/bin/bash

# Study Assistant — bundle updater (the family installer contract)
#
# Updates an install made by scripts/install.sh from a NEW source-free
# release bundle (extracted over the existing install directory — the bundle
# carries no .env, so the env file and its secrets survive):
#   records and keeps the previous image pin → bumps STUDY_IMAGE to the
#   new release (flags, $STUDY_IMAGE, or the manifest.json shipped next to
#   the new bundle) → pull → up -d → wait for /api/v1/health.
#
# Usage (from the new bundle's root, over the existing install):
#   bash scripts/update.sh                     # pin from manifest.json when present
#   bash scripts/update.sh --image app=ghcr.io/…@sha256:…   # pin-passing form
#   bash scripts/update.sh --image-tag 0.13.2  # pin to a release tag
#   bash scripts/update.sh --no-pull           # reuse local images
#   bash scripts/update.sh --no-wait           # skip the health wait
#   bash scripts/update.sh -h|--help          # this help
#
# No git, no destructive data operations: this script never pulls source,
# never removes volumes and never touches secrets in the env file (the only
# writes are the STUDY_IMAGE pin and a comment recording the previous pin).
# Take a backup first — scripts/backup.sh — pre-1.0 schema migrations have
# no downgrade path.
#
# Rollback: the previous pin is printed and kept as a comment in the env
# file — restore it with:
#   bash scripts/update.sh --image <previous pin>
# and restore data from the pre-upgrade backup when needed.
#
# Exit codes (the installer contract): 0 ok · 1 usage/prerequisite ·
# 2 image verify/pull · 3 compose start or health-wait · 4 port conflict.

set -euo pipefail

print_help() {
    sed -n '3,/^[^#]/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
    exit 0
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib-docker.sh"

# ── flags ───────────────────────────────────────────────────────────────────
NO_PULL=0 NO_WAIT=0
IMAGE_TAG_ARG="" ALLOW_ROOT="${ALLOW_ROOT:-}"
IMAGE_ARGS=()   # --image values ([KEY=]REF), resolved after the config load
while [ "$#" -gt 0 ]; do
    case "$1" in
        -h|--help) print_help ;;
        --no-pull) NO_PULL=1 ;;
        --no-wait) NO_WAIT=1 ;;
        --allow-root) ALLOW_ROOT=1 ;;
        --image)
            [ "$#" -ge 2 ] || die "--image needs a value ([KEY=]REF)"
            IMAGE_ARGS+=("$2"); shift ;;
        --image-tag)
            [ "$#" -ge 2 ] || die "--image-tag needs a value"
            IMAGE_TAG_ARG="$2"; shift ;;
        *)
            echo -e "${RED}Unknown parameter: $1 (try --help)${NC}" >&2
            exit 1
            ;;
    esac
    shift
done

# ── pre-flight ────────────────────────────────────────────────────────────────
if [ "$(id -u)" = "0" ] && [ -z "$ALLOW_ROOT" ]; then
    echo -e "${RED}Refusing to run as root (the installer contract: no root, no sudo).${NC}" >&2
    echo "  Re-run as your normal account; CI/disposable containers only: --allow-root" >&2
    exit 1
fi

[ -f docker/docker-compose.standalone.yml ] \
    || die "run this from the extracted bundle root (the directory holding docker/ and scripts/)"
check_docker
[ "$DOCKER_COMPOSE_CMD" = "docker compose" ] \
    || die "Docker Compose v2 ('docker compose') is required; legacy docker-compose v1 cannot run the standalone stack."

# Study's env-file decision: docker/.env first, root .env when only that
# exists (a source-checkout legacy install keeps working).
resolve_env_file
[ -f "$ENV_FILE" ] \
    || die "${ENV_FILE} not found — this is not an existing install. Run scripts/install.sh first."

# Product config (installer.json ships with the bundle; installer/1) —
# only schema fields are read.
HEALTH_PATH="$(json_field installer.json healthPath)"; [ -n "$HEALTH_PATH" ] || HEALTH_PATH="/api/v1/health"
# readyPath null = not shipped at this release — print no Ready line, never probe.
READY_PATH="$(json_field installer.json readyPath)"
IMAGE_ENV="$(json_field installer.json imageEnv)"; [ -n "$IMAGE_ENV" ] || IMAGE_ENV="STUDY_IMAGE"
IMAGE_KEYS="$(json_keys installer.json imageKeys)"
if [ -z "$IMAGE_KEYS" ]; then
    echo -e "${YELLOW}Could not read imageKeys from installer.json — accepting 'app' only.${NC}"
    IMAGE_KEYS="app"
fi

HTTP_PORT="$(env_value HTTP_PORT 80)"
HEALTH_URL="http://127.0.0.1:${HTTP_PORT}${HEALTH_PATH}"

# ── the new pin (--image [KEY=]REF > --image-tag > $STUDY_IMAGE > the new
# bundle's manifest.json > keep the current pin) ──────────────────────────────
manifest_primary_pin() {
    local K REF
    for K in $IMAGE_KEYS; do
        REF="$(json_field manifest.json "images.$K")"
        [ -n "$REF" ] && { printf '%s' "$REF"; return 0; }
    done
    printf ''
}

image_repo_hint() { # repository part of a ref — derived, never hardcoded
    case "$1" in
        *@sha256:*) printf '%s' "${1%%@*}" ;;
        *:*)       printf '%s' "${1%%:*}" ;;
        *)         printf '%s' "$1" ;;
    esac
}

env_image_ref() { printf '%s' "${!1:-}"; }

MANIFEST_IMAGE="$(manifest_primary_pin)"
NEW_PIN=""
OPERATOR_TYPED=0
for ARG in ${IMAGE_ARGS[@]+"${IMAGE_ARGS[@]}"}; do
    KEY=""
    REF="$ARG"
    # Image refs never contain '=': a value that does is the bootstrap's
    # KEY=REF pin-passing form (the hand-off form the one-liner uses).
    case "$ARG" in
        *=*) KEY="${ARG%%=*}"; REF="${ARG#*=}" ;;
    esac
    if [ -n "$KEY" ]; then
        case " $IMAGE_KEYS " in
            *" $KEY "*) ;;
            *) die "unknown image key '$KEY' in --image '$ARG' — this product's imageKeys: ${IMAGE_KEYS}" ;;
        esac
    fi
    NEW_PIN="$REF"
    OPERATOR_TYPED=1
done
if [ -z "$NEW_PIN" ] && [ -n "$IMAGE_TAG_ARG" ]; then
    TAG="${IMAGE_TAG_ARG#v}"
    case "$TAG" in
        [0-9]*.[0-9]*.[0-9]*) ;;
        *) die "--image-tag must look like X.Y.Z or vX.Y.Z (got: $IMAGE_TAG_ARG)" ;;
    esac
    REPO_SRC="$MANIFEST_IMAGE"
    [ -z "$REPO_SRC" ] && REPO_SRC="$(env_value "$IMAGE_ENV" '')"
    [ -n "$REPO_SRC" ] \
        || die "--image-tag needs manifest.json (or the existing pin) to resolve the image repository — pass --image ${IMAGE_KEYS%% *}=<full ref> instead."
    NEW_PIN="$(image_repo_hint "$REPO_SRC"):${TAG}"
    OPERATOR_TYPED=1
fi
if [ -z "$NEW_PIN" ] && [ -n "$(env_image_ref "$IMAGE_ENV")" ]; then
    NEW_PIN="$(env_image_ref "$IMAGE_ENV")"
    OPERATOR_TYPED=1
fi
[ -z "$NEW_PIN" ] && [ -n "$MANIFEST_IMAGE" ] && NEW_PIN="$MANIFEST_IMAGE"
[ -n "$NEW_PIN" ] || echo -e "${GREEN}No new pin found — refreshing the current release.${NC}"

# Operator-typed mutable pins are refused here; manifest-sourced pins are
# checked against the rendered compose model below (exit 3).
if [ "$OPERATOR_TYPED" -eq 1 ]; then
    case "${NEW_PIN:-}" in
        *:latest|*:main)
            die "Refusing the mutable pin '${NEW_PIN}' — latest/main float with the develop branch and can break the migrate step. The installer contract pins releases only; pass a release tag or a digest."
            ;;
    esac
fi

IMAGE_PIN="$(env_value "$IMAGE_ENV" '')"
if [ -n "$NEW_PIN" ] && [ "$NEW_PIN" != "$IMAGE_PIN" ]; then
    # Keep the previous pin (rollback): a comment in the env file
    # (compose ignores comments) plus the printed rollback command.
    printf '# previous %s (kept by scripts/update.sh %s): %s\n' \
        "$IMAGE_ENV" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$IMAGE_PIN" >> "$ENV_FILE"
    set_env_value "$IMAGE_ENV" "$NEW_PIN"
    echo -e "${GREEN}Image pin moved: ${IMAGE_PIN:-<none>} → ${NEW_PIN}${NC}"
    echo -e "${YELLOW}Rollback (previous pin kept in ${ENV_FILE}):${NC}"
    echo "  bash scripts/update.sh --image ${IMAGE_PIN:-<previous pin>}"
    IMAGE_PIN="$NEW_PIN"
elif [ -n "$IMAGE_PIN" ]; then
    echo -e "${GREEN}Keeping the current image pin: ${IMAGE_PIN}${NC}"
fi

# refresh_images / up_stack key off the shell variable (study's pattern);
# compose reads the same pin from the env file at interpolation time.
[ -n "$IMAGE_PIN" ] && export STUDY_IMAGE="$IMAGE_PIN"
if [ -z "$IMAGE_PIN" ]; then
    echo -e "${YELLOW}No pin in ${ENV_FILE} — a source-free bundle has nothing to build.${NC}" >&2
    echo "  Pass --image ${IMAGE_KEYS%% *}=<ref>, --image-tag X.Y.Z, or ship the release manifest.json." >&2
fi

# ── port pre-flight (the running stack's own ports pass; a foreign holder of
# the port means something else grabbed it — stop before touching images) ────
check_published_ports

# ── image verification ───────────────────────────────────────────────────────
# Rendered compose model vs the pin; mutable refs never reach up -d.
# Exit 3 (fixtures manifest-image-compose-assert / mutable-compose-ref-refused).
if [ -n "$IMAGE_PIN" ] && command -v python3 &>/dev/null; then
    RENDERED="$(run_compose config --format json 2>/dev/null | python3 -c '
import json, sys
try:
    model = json.load(sys.stdin)
except Exception:
    sys.exit(1)
for name in ("app", "migrate"):
    svc = (model.get("services") or {}).get(name) or {}
    print(svc.get("image") or "")
' 2>/dev/null || true)"
    if [ -n "$RENDERED" ]; then
        while IFS= read -r IMG; do
            [ -n "$IMG" ] || continue
            case "$IMG" in
                *:latest|*:main)
                    echo -e "${RED}Mutable image ref refused: compose resolved '${IMG}' — latest/main never reach rendered Compose (the installer contract pins releases only).${NC}" >&2
                    exit 3
                    ;;
            esac
            if [ "$IMG" != "$IMAGE_PIN" ]; then
                echo -e "${RED}Image verification failed: compose resolved '${IMG}' but the release pin (manifest.json / ${IMAGE_ENV}) is '${IMAGE_PIN}'.${NC}" >&2
                exit 3
            fi
        done <<< "$RENDERED"
        echo -e "${GREEN}Image pin verified: ${IMAGE_PIN}${NC}"
    fi
fi

# ── pull ─────────────────────────────────────────────────────────────────────
# refresh_images is study's pull helper: it pulls exactly when a registry
# pin is in play (STUDY_IMAGE, exported above) and never tries to build.
if [ "$NO_PULL" -eq 0 ]; then
    echo -e "${GREEN}Pulling the pinned images...${NC}"
    if ! refresh_images; then
        echo -e "${RED}Image pull failed (offline host? registry auth?).${NC}" >&2
        echo "  The previous containers keep running. Re-run with --no-pull to reuse" >&2
        echo "  local images, or fix the network/credentials." >&2
        exit 2
    fi
fi

# One-time ADR-0022 DB/role rename (neuro_* → neuronection_*), before the
# stack boots against the new names. No-op on fresh installs and re-runs.
migrate_legacy_db_names

echo -e "${GREEN}Recreating the standalone stack...${NC}"
# up_stack is study's start helper: `up -d --no-build` under a pin.
if ! up_stack; then
    echo -e "${RED}docker compose up failed (exit above).${NC}" >&2
    report_compose_failure
    echo -e "${YELLOW}Rollback: bash scripts/update.sh --image <previous pin>${NC}" >&2
    exit 3
fi

if [ "$NO_WAIT" -eq 0 ]; then
    wait_for_backend_healthy || exit 3
fi

echo
echo -e "${GREEN}Update complete.${NC}"
echo "  URL:      http://$(hostname 2>/dev/null || echo localhost):${HTTP_PORT}"
echo "  Health:   ${HEALTH_URL}"
# readyPath null = /ready not shipped at this release — no line, no probe.
[ -n "$READY_PATH" ] && echo "  Ready:    http://127.0.0.1:${HTTP_PORT}${READY_PATH}"
echo "  Rollback: the previous pin is kept in ${ENV_FILE}; data via scripts/restore.sh"
