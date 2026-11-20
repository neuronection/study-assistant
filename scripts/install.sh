#!/bin/bash

# Study Assistant — bundle installer (the family installer contract)
#
# Runs INSIDE the extracted source-free release bundle (the directory holding
# docker/ and scripts/) and takes a fresh host to a running standalone stack:
#   pre-flight (Docker/Compose v2, no root) → env file (generate the five
#   per-instance secrets, keep an existing one) → pin the image from the
#   release manifest / flags → port pre-flight → pull → up -d → wait for
#   /api/v1/health → summary with URL, first-admin note, backup/update/
#   rollback hints.
#
# Usage (from the extracted bundle root):
#   bash scripts/install.sh                            # install + start (port 8091 — the family default; 8090=health, 8092=career)
#   bash scripts/install.sh --http-port 8091           # publish nginx on 8091
#   bash scripts/install.sh --public-url https://study.example.com    # public URL (SA_PUBLIC_URL) — pins Secure cookies, CORS/OAuth
#   bash scripts/install.sh --bind 127.0.0.1           # publish on loopback only (behind your own reverse proxy)
#   bash scripts/install.sh --image app=ghcr.io/…@sha256:…   # pin-passing form (what the bootstrap forwards)
#   bash scripts/install.sh --image-tag 0.13.1         # pin a published release tag
#   bash scripts/install.sh --env-only                 # write the env file only
#   bash scripts/install.sh --no-pull                  # reuse local images (offline)
#   bash scripts/install.sh --no-wait                  # skip the /api/v1/health wait
#   bash scripts/install.sh --auto-ports               # move busy ports to free ones
#   bash scripts/install.sh --no-ports                 # skip the port pre-flight
#   bash scripts/install.sh --reset --yes              # wipe stack volumes, reinstall
#   bash scripts/install.sh -h|--help                  # this help
#
# Image pin priority (the contract's hand-off order): --image [KEY=]REF >
# --image-tag TAG > $STUDY_IMAGE (environment) > manifest.json next to this
# bundle > the pin already in the env file. KEY=REF names one image slot
# from installer.json's imageKeys (study: app); a bare REF overrides the
# primary image. This is a source-free bundle: without a pin there is
# nothing to build, so the installer refuses. In a full source checkout
# scripts/run-docker.sh is the build path.
#
# Idempotent: a re-run keeps the env file (secrets are never overwritten and
# never printed), refreshes images via study's refresh_images and re-runs
# up_stack (up -d --no-build under a pin). Data volumes are never touched
# except by the explicit --reset.
#
# Study keeps its docker/.env → root .env fallback: an existing root .env of
# a source-checkout install is honored and left untouched (docker/.env is
# the family convention; the installer creates it when neither exists).
#
# Exit codes (the installer contract): 0 ok · 1 usage/prerequisite ·
# 2 image pull (download) · 3 compose config/start or health-wait ·
# 4 port conflict.

set -euo pipefail

print_help() {
    sed -n '3,/^[^#]/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
    exit 0
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib-docker.sh"

# ── flags ───────────────────────────────────────────────────────────────────
ENV_ONLY=0 NO_PULL=0 NO_WAIT=0 AUTO_PORTS=0 NO_PORTS=0 RESET=0 RESET_YES=0
IMAGE_TAG_ARG="" HTTP_PORT_ARG="" PUBLIC_URL_ARG="" BIND_ARG="" ALLOW_ROOT="${ALLOW_ROOT:-}"
IMAGE_ARGS=()   # --image values ([KEY=]REF), resolved after the config load
while [ "$#" -gt 0 ]; do
    case "$1" in
        -h|--help) print_help ;;
        --env-only) ENV_ONLY=1 ;;
        --no-pull) NO_PULL=1 ;;
        --no-wait) NO_WAIT=1 ;;
        --auto-ports) AUTO_PORTS=1 ;;
        --no-ports) NO_PORTS=1 ;;
        --reset) RESET=1 ;;
        --yes) RESET_YES=1 ;;
        --allow-root) ALLOW_ROOT=1 ;;
        --image)
            [ "$#" -ge 2 ] || die "--image needs a value ([KEY=]REF)"
            IMAGE_ARGS+=("$2"); shift ;;
        --image-tag)
            [ "$#" -ge 2 ] || die "--image-tag needs a value"
            IMAGE_TAG_ARG="$2"; shift ;;
        --public-url)
            [ "$#" -ge 2 ] || die "--public-url needs a value"
            PUBLIC_URL_ARG="$2"; shift ;;
        --bind)
            [ "$#" -ge 2 ] || die "--bind needs an IP address"
            BIND_ARG="$2"; shift ;;
        --http-port)
            [ "$#" -ge 2 ] || die "--http-port needs a value"
            case "$2" in ''|*[!0-9]*) die "--http-port needs a numeric PORT (got: $2)" ;; esac
            HTTP_PORT_ARG="$2"; shift ;;
        *)
            echo -e "${RED}Unknown parameter: $1 (try --help)${NC}" >&2
            exit 1
            ;;
    esac
    shift
done

# ── pre-flight ──────────────────────────────────────────────────────────────
# No root, no sudo (the installer contract): the stack runs entirely
# through Docker as an unprivileged user. --allow-root exists for CI and
# disposable smoke containers only.
if [ "$(id -u)" = "0" ] && [ -z "$ALLOW_ROOT" ]; then
    echo -e "${RED}Refusing to run as root (the installer contract: no root, no sudo).${NC}" >&2
    echo "  Re-run as your normal account (add it to the docker group if needed:" >&2
    echo "  sudo usermod -aG docker <user>, then log in again)." >&2
    echo "  CI/disposable containers only: --allow-root" >&2
    exit 1
fi
[ -n "$ALLOW_ROOT" ] && echo -e "${YELLOW}--allow-root: continuing as root (CI/disposable use only).${NC}"

if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
    echo "bash >= 4 is required (found ${BASH_VERSION:-unknown})." >&2
    exit 1
fi

[ -f docker/docker-compose.standalone.yml ] \
    || die "run this from the extracted bundle root (the directory holding docker/ and scripts/)"

check_docker
# The standalone stack relies on compose-spec features (service_completed_
# successfully) — the v1 fallback lib-docker.sh tolerates elsewhere is not
# enough here.
[ "$DOCKER_COMPOSE_CMD" = "docker compose" ] \
    || die "Docker Compose v2 ('docker compose') is required; legacy docker-compose v1 cannot run the standalone stack."

INSTALL_DIR="$(pwd)"

# Study's env-file decision: docker/.env first, root .env when only that
# exists, docker/.env (created below) when neither does.
resolve_env_file

# ── product config (installer.json ships with the bundle) ───────────────────
# Only installer.json's schema fields are read; everything
# product-specific is derived, never hardcoded twice.
HEALTH_PATH="$(json_field installer.json healthPath)"; [ -n "$HEALTH_PATH" ] || HEALTH_PATH="/api/v1/health"
# readyPath null = not shipped at this release (study adds /ready with its
# T1 conformance): print no Ready line and never probe it.
READY_PATH="$(json_field installer.json readyPath)"
DOCS_URL="$(json_field installer.json docsUrl)"; [ -n "$DOCS_URL" ] || DOCS_URL="https://neuronection.com/docs/study"
IMAGE_ENV="$(json_field installer.json imageEnv)"; [ -n "$IMAGE_ENV" ] || IMAGE_ENV="STUDY_IMAGE"
IMAGE_KEYS="$(json_keys installer.json imageKeys)"
if [ -z "$IMAGE_KEYS" ]; then
    echo -e "${YELLOW}Could not read imageKeys from installer.json — accepting 'app' only.${NC}"
    IMAGE_KEYS="app"
fi
DEFAULT_PORT="$(json_field installer.json defaultPort)"
case "$DEFAULT_PORT" in ''|*[!0-9]*) DEFAULT_PORT=8091 ;; esac
MIN_RAM_GB="$(json_field installer.json minRamGb)"
case "$MIN_RAM_GB" in ''|*[!0-9]*) MIN_RAM_GB=4 ;; esac
# The setup hint derives from setupMode (the schema's closed vocabulary).
SETUP_MODE="$(json_field installer.json setupMode)"
case "$SETUP_MODE" in
    "first user = admin") SETUP_HINT="Open the URL and register — the first user becomes the admin." ;;
    "setup token")        SETUP_HINT="Open the setup URL printed once by the installer." ;;
    *)                    SETUP_HINT="Open the URL and complete the first-run setup." ;;
esac
MANIFEST_VERSION="$(json_field manifest.json version)"

# RAM/disk hints — never a hard fail (containers may not expose meminfo).
if [ -r /proc/meminfo ]; then
    MEM_MB="$(awk '/^MemTotal:/ {print int($2/1024); exit}' /proc/meminfo 2>/dev/null || true)"
    if [ -n "$MEM_MB" ] && [ "$MEM_MB" -lt "$((MIN_RAM_GB * 1024))" ]; then
        echo -e "${YELLOW}RAM hint: ${MIN_RAM_GB} GB is the family minimum; this host reports ${MEM_MB} MB.${NC}"
    fi
fi
if command -v df >/dev/null 2>&1; then
    AVAIL_MB="$(df -Pm . 2>/dev/null | awk 'NR==2 {print $4}' || true)"
    if [ -n "$AVAIL_MB" ] && [ "$AVAIL_MB" -gt 0 ] && [ "$AVAIL_MB" -lt 5120 ]; then
        echo -e "${YELLOW}Disk hint: ${AVAIL_MB} MB free — image pulls and uploads need headroom.${NC}"
    fi
fi

# ── image pin (pinned releases only — never latest) ─────────────────────────
# The manifest's image slots for this product (installer.json imageKeys —
# study declares exactly "app").
manifest_primary_pin() {
    local K REF
    for K in $IMAGE_KEYS; do
        REF="$(json_field manifest.json "images.$K")"
        [ -n "$REF" ] && { printf '%s' "$REF"; return 0; }
    done
    printf ''
}

# The repository part of an image ref (strip @sha256:… or :tag) — derived
# from the manifest/existing pin, never a second hardcoded constant.
image_repo_hint() {
    case "$1" in
        *@sha256:*) printf '%s' "${1%%@*}" ;;
        *:*)       printf '%s' "${1%%:*}" ;;
        *)         printf '%s' "$1" ;;
    esac
}

# $<IMAGE_ENV> from the shell (the contract's <P>_IMAGE override), set -u safe.
env_image_ref() {
    printf '%s' "${!1:-}"
}

MANIFEST_IMAGE="$(manifest_primary_pin)"
IMAGE_PIN=""
OPERATOR_TYPED=0
# 1. --image [KEY=]REF — the bootstrap forwards one per manifest image, a
#    bare REF last (user override wins). KEY must be one of imageKeys.
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
    IMAGE_PIN="$REF"
    OPERATOR_TYPED=1
done
# 2. --image-tag X.Y.Z → <repo>:X.Y.Z, the repo derived from the manifest
#    (or the existing pin) — installer.json carries no repo constant.
if [ -z "$IMAGE_PIN" ] && [ -n "$IMAGE_TAG_ARG" ]; then
    TAG="${IMAGE_TAG_ARG#v}"
    case "$TAG" in
        [0-9]*.[0-9]*.[0-9]*) ;;
        *) die "--image-tag must look like X.Y.Z or vX.Y.Z (got: $IMAGE_TAG_ARG)" ;;
    esac
    REPO_SRC="$MANIFEST_IMAGE"
    [ -z "$REPO_SRC" ] && REPO_SRC="$(env_value "$IMAGE_ENV" '')"
    [ -n "$REPO_SRC" ] \
        || die "--image-tag needs manifest.json (or an existing pin) to resolve the image repository — pass --image ${IMAGE_KEYS%% *}=<full ref> instead."
    IMAGE_PIN="$(image_repo_hint "$REPO_SRC"):${TAG}"
    OPERATOR_TYPED=1
fi
# 3. the contract's env override ($STUDY_IMAGE per envPrefix/imageEnv).
if [ -z "$IMAGE_PIN" ] && [ -n "$(env_image_ref "$IMAGE_ENV")" ]; then
    IMAGE_PIN="$(env_image_ref "$IMAGE_ENV")"
    OPERATOR_TYPED=1
fi
# 4. the release manifest next to this bundle.
[ -z "$IMAGE_PIN" ] && [ -n "$MANIFEST_IMAGE" ] && IMAGE_PIN="$MANIFEST_IMAGE"
# 5. the pin already in the env file (re-run).
[ -z "$IMAGE_PIN" ] && IMAGE_PIN="$(env_value "$IMAGE_ENV" '')"

if [ -n "$IMAGE_PIN" ]; then
    # Operator-typed mutable refs are refused here, before anything is
    # written; manifest/env-file-sourced pins hit the same wall later,
    # against the RENDERED compose model (exit 3 — a compose-config
    # failure, before anything is pulled or started).
    if [ "$OPERATOR_TYPED" -eq 1 ]; then
        case "$IMAGE_PIN" in
            *:latest|*:main)
                die "Refusing the mutable pin '${IMAGE_PIN}' — latest/main float with the develop branch and can break the migrate step. The installer contract pins releases only; pass a release tag or a digest."
                ;;
        esac
    fi
    # refresh_images / up_stack key off the shell variable (study's
    # pattern); compose reads the same pin from the env file at
    # interpolation time, where it is persisted below.
    export STUDY_IMAGE="$IMAGE_PIN"
else
    if [ "$ENV_ONLY" -eq 1 ]; then
        echo -e "${YELLOW}Warning: no image pin found — ${ENV_FILE} will be written without one.${NC}"
        echo "  Set it before starting: --image ${IMAGE_KEYS%% *}=<ref>, --image-tag X.Y.Z, or"
        echo "  ${IMAGE_ENV}=<ref>, or place the release manifest.json next to this bundle and re-run."
    else
        echo -e "${RED}No image pin. This is a source-free bundle — there is nothing to build.${NC}" >&2
        echo "  Pick one:" >&2
        echo "    * recommended: place manifest.json (from the same GitHub release) next to" >&2
        echo "      this bundle — the installer pins the exact image digest from it;" >&2
        echo "    * or re-run with --image-tag X.Y.Z (a published release tag);" >&2
        echo "    * or set ${IMAGE_ENV}=<registry image or digest ref> and re-run." >&2
        echo "  In a full source checkout, scripts/run-docker.sh is the build path." >&2
        exit 1
    fi
fi

# Release-skew guard: a hand-passed --image-tag must agree with the bundle's
# own manifest (the tree and the images must describe the same contract).
if [ -n "$IMAGE_TAG_ARG" ] && [ -n "$MANIFEST_VERSION" ]; then
    MV="${MANIFEST_VERSION#v}"
    if [ "$MV" != "${IMAGE_TAG_ARG#v}" ]; then
        die "--image-tag ${IMAGE_TAG_ARG} does not match this bundle's manifest (version ${MV}). Pin the matching release, or drop --image-tag and let the manifest pin it."
    fi
fi

# ── host port ────────────────────────────────────────────────────────────────
HTTP_PORT="${HTTP_PORT_ARG:-${STUDY_HTTP_PORT:-$(env_value HTTP_PORT '')}}"
[ -n "$HTTP_PORT" ] || HTTP_PORT="$DEFAULT_PORT"
case "$HTTP_PORT" in ''|*[!0-9]*) die "HTTP_PORT must be numeric (got: $HTTP_PORT)" ;; esac
HEALTH_URL="http://127.0.0.1:${HTTP_PORT}${HEALTH_PATH}"

# ── bind address (optional; default 0.0.0.0, loopback behind your proxy) ───
HTTP_BIND="${BIND_ARG:-${STUDY_HTTP_BIND:-$(env_value HTTP_BIND '')}}"
[ -n "$HTTP_BIND" ] || HTTP_BIND="0.0.0.0"
[ "$HTTP_BIND" = "localhost" ] && HTTP_BIND="127.0.0.1"   # compose needs an IP literal
case "$HTTP_BIND" in
    *[!0-9.]*) die "--bind must be an IP address like 127.0.0.1 (got: $HTTP_BIND)" ;;
esac
IFS='.' read -r B1 B2 B3 B4 <<BIND_EOF
$HTTP_BIND
BIND_EOF
for B in "$B1" "$B2" "$B3" "$B4"; do
    case "$B" in ''|*[!0-9]*) die "--bind must be an IPv4 address like 127.0.0.1 (got: $HTTP_BIND)" ;; esac
    [ "$B" -le 255 ] || die "--bind octet out of range in ${HTTP_BIND}"
done

# ── env file (never overwrite an existing one) ───────────────────────────────
gen_secret() { # [BYTES] → urlsafe random token (32 bytes default)
    local BYTES="${1:-32}"
    if command -v python3 &>/dev/null; then
        python3 -c 'import secrets, sys; print(secrets.token_urlsafe(int(sys.argv[1])))' "$BYTES"
    elif command -v base64 &>/dev/null; then
        # 32 bytes → 44-char urlsafe base64. The session/refresh keys take
        # any strong string; the data key uses gen_fernet_key below.
        head -c "$BYTES" /dev/urandom | base64 | tr '+/' '-_'
    else
        die "Cannot generate secrets: python3 (or coreutils base64) is required."
    fi
}

# A Fernet key (the SA_DATA_KEY shape): 32 random bytes, urlsafe base64 with
# padding — exactly what cryptography.fernet.Fernet.generate_key() produces,
# from the stdlib alone.
gen_fernet_key() {
    python3 -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'
}

ENV_WAS_FRESH=0
if [ -f "$ENV_FILE" ]; then
    echo -e "${GREEN}${ENV_FILE} already exists — leaving it untouched (secrets, pin and port are kept).${NC}"
else
    [ -f docker/.env.production.example ] \
        || die "docker/.env.production.example is missing — this is not a complete bundle."
    echo -e "${GREEN}No ${ENV_FILE} found — creating one from the example and generating fresh secrets.${NC}"
    ( umask 077; cp docker/.env.production.example "$ENV_FILE" )
    chmod 600 "$ENV_FILE"
    # Study's five per-instance secrets (the compose :? guards fail closed
    # without them): the key family + the two split DB credentials.
    set_env_value SA_SESSION_KEY "$(gen_secret 32)"
    set_env_value SA_REFRESH_KEY "$(gen_secret 32)"
    set_env_value SA_DATA_KEY "$(gen_fernet_key)"
    OWNER_PW="$(gen_secret 24)"
    APP_PW="$(gen_secret 24)"
    # Distinct owner/app passwords (the credential split).
    while [ "$OWNER_PW" = "$APP_PW" ]; do APP_PW="$(gen_secret 24)"; done
    set_env_value SA_DB_OWNER_PASSWORD "$OWNER_PW"
    set_env_value SA_DB_PASSWORD "$APP_PW"
    echo -e "${GREEN}Generated fresh per-instance secrets (values not printed).${NC}"
    ENV_WAS_FRESH=1
fi

# Persist the resolved pin and port only when they change (a re-run of the
# same release must be a byte-for-byte no-op on the env file).
if [ -n "$IMAGE_PIN" ] && [ "$IMAGE_PIN" != "$(env_value "$IMAGE_ENV" '')" ]; then
    set_env_value "$IMAGE_ENV" "$IMAGE_PIN"
    echo -e "${GREEN}Pinned ${IMAGE_ENV}=${IMAGE_PIN} (saved in ${ENV_FILE}).${NC}"
fi
# Update-path guard: an install made before the 8091 default must not
# silently move ports on a re-run. If the env file predates persisted
# ports (no HTTP_PORT in it) and nothing was passed explicitly, keep the
# historical 80 and say so loudly.
if [ "$ENV_WAS_FRESH" -eq 0 ] && [ -z "$HTTP_PORT_ARG" ] && [ -z "${STUDY_HTTP_PORT:-}" ] \
   && [ -z "$(env_value HTTP_PORT '')" ] && [ "$HTTP_PORT" != "80" ]; then
    echo -e "${YELLOW}This install predates persisted ports: keeping HTTP_PORT=80 (the old default) — set --http-port 8091 to move it.${NC}"
    HTTP_PORT=80
fi
if [ "$HTTP_PORT" != "$(env_value HTTP_PORT '')" ]; then
    set_env_value HTTP_PORT "$HTTP_PORT"
    echo -e "${GREEN}Set HTTP_PORT=${HTTP_PORT} (saved in ${ENV_FILE}).${NC}"
fi
# Persist the bind only when explicitly chosen (flag or env): a re-run
# with no input must stay a byte-for-byte no-op on the env file.
if [ -n "$BIND_ARG" ] || [ -n "${STUDY_HTTP_BIND:-}" ]; then
    if [ "$HTTP_BIND" != "$(env_value HTTP_BIND '')" ]; then
        set_env_value HTTP_BIND "$HTTP_BIND"
        echo -e "${GREEN}Set HTTP_BIND=${HTTP_BIND} (saved in ${ENV_FILE}).${NC}"
    fi
fi
# Explicit public URL: persist SA_PUBLIC_URL (drives Secure cookies,
# CORS and OAuth redirects; http:// keeps LAN logins working).
if [ -n "$PUBLIC_URL_ARG" ]; then
    case "$PUBLIC_URL_ARG" in
        *://*) PUBLIC_URL_ARG="${PUBLIC_URL_ARG%/}" ;;
        *)      PUBLIC_URL_ARG="http://${PUBLIC_URL_ARG%/}" ;;
    esac
    if [ "$PUBLIC_URL_ARG" != "$(env_value SA_PUBLIC_URL '')" ]; then
        set_env_value SA_PUBLIC_URL "$PUBLIC_URL_ARG"
        echo -e "${GREEN}Set SA_PUBLIC_URL=${PUBLIC_URL_ARG} (saved in ${ENV_FILE}).${NC}"
    fi
fi
# The port may have moved in the pre-flight below; keep the health URL honest.
HEALTH_URL="http://127.0.0.1:$(env_value HTTP_PORT "$HTTP_PORT")${HEALTH_PATH}"
HTTP_PORT="$(env_value HTTP_PORT "$HTTP_PORT")"

# A fresh env file cannot log into a database volume left by a previous
# install (postgres only applies POSTGRES_PASSWORD on first init) — say so
# before the migrate job fails with a confusing auth error. Warning only:
# the deliberate reset path is --reset.
if [ "$ENV_WAS_FRESH" = "1" ]; then
    PG_VOL="$(resolve_compose_project)_db_data"
    if docker volume inspect "$PG_VOL" >/dev/null 2>&1; then
        echo -e "${YELLOW}Warning: a previous install's database volume exists (${PG_VOL}).${NC}"
        echo "  The freshly generated credentials will not match it. Either restore your" >&2
        echo "  previous ${ENV_FILE}, or wipe it deliberately: bash scripts/install.sh --reset --yes" >&2
    fi
fi

# ── --env-only: stop after the environment is ready ─────────────────────────
if [ "$ENV_ONLY" -eq 1 ]; then
    echo
    echo -e "${GREEN}Done — ${ENV_FILE} is ready. Start the stack with:${NC}"
    echo "  bash scripts/install.sh"
    echo "  (then: ${HEALTH_URL})"
    exit 0
fi

# ── --reset: deliberate, destructive, confirmed ──────────────────────────────
if [ "$RESET" -eq 1 ]; then
    PROJECT="$(resolve_compose_project)"
    DB_VOL="${PROJECT}_db_data"
    DATA_VOL="${PROJECT}_data"
    echo -e "${RED}Reset: this permanently deletes the stack's data volumes:${NC}"
    echo "  ${DB_VOL}   (database)"
    echo "  ${DATA_VOL}   (uploads, blobs, cache, import-inbox)"
    echo "  ${ENV_FILE} is kept."
    if [ "$RESET_YES" -ne 1 ]; then
        if ! read -r -p "Type 'yes' to confirm and reset: " REPLY; then
            die "--reset needs --yes when not run interactively."
        fi
        [ "$REPLY" = "yes" ] || die "Aborted — nothing was changed."
    fi
    echo -e "${YELLOW}Stopping the stack...${NC}"
    run_compose down >/dev/null 2>&1 || true
    for VOL in "$DB_VOL" "$DATA_VOL"; do
        if docker volume inspect "$VOL" >/dev/null 2>&1; then
            docker volume rm "$VOL" >/dev/null 2>&1 \
                && echo -e "${GREEN}Removed ${VOL}${NC}" \
                || echo -e "${YELLOW}Could not remove ${VOL} (left in place)${NC}"
        else
            echo -e "${GREEN}${VOL} did not exist — nothing to remove.${NC}"
        fi
    done
    echo -e "${GREEN}Data reset complete — the stack will start from empty storage.${NC}"
fi

# ── port pre-flight (before anything is pulled or started) ──────────────────
if [ "$NO_PORTS" -eq 0 ]; then
    if [ "$AUTO_PORTS" -eq 1 ]; then
        check_published_ports --auto
    else
        check_published_ports
    fi
    # --auto-ports may have moved the port in the env file.
    HEALTH_URL="http://127.0.0.1:$(env_value HTTP_PORT "$HTTP_PORT")${HEALTH_PATH}"
    HTTP_PORT="$(env_value HTTP_PORT "$HTTP_PORT")"
fi

# ── image verification (the installer asserts the resolved image) ───────────
# The rendered compose model is the single wall for manifest/env-file-sourced
# pins: rendered image(s) must match the release pin and must never be a
# mutable ref. Exit 3 (compose config failure); operator-typed mutable refs
# were already refused at pin resolution, so this catches manifest drift,
# stale env-file pins and tampered manifests.
assert_rendered_image() {
    command -v python3 &>/dev/null || {
        echo -e "${YELLOW}Skipping the image assert (python3 unavailable).${NC}"
        return 0
    }
    [ -n "$IMAGE_PIN" ] || return 0
    local RENDERED IMG
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
    [ -n "$RENDERED" ] || { echo -e "${YELLOW}Skipping the image assert (compose model not renderable).${NC}"; return 0; }
    while IFS= read -r IMG; do
        [ -n "$IMG" ] || continue
        case "$IMG" in
            *:latest|*:main)
                echo -e "${RED}Mutable image ref refused: compose resolved '${IMG}' — latest/main never reach rendered Compose (the installer contract pins releases only).${NC}" >&2
                echo "  Fix the ${IMAGE_ENV} pin in ${ENV_FILE} (or manifest.json) to a release digest/tag and re-run." >&2
                exit 3
                ;;
        esac
        if [ "$IMG" != "$IMAGE_PIN" ]; then
            echo -e "${RED}Image verification failed: compose resolved '${IMG}' but the release pin (manifest.json / ${IMAGE_ENV}) is '${IMAGE_PIN}'.${NC}" >&2
            echo "  ${ENV_FILE} and docker/docker-compose.standalone.yml disagree about the image." >&2
            exit 3
        fi
    done <<< "$RENDERED"
    echo -e "${GREEN}Image pin verified: ${IMAGE_PIN}${NC}"
}
assert_rendered_image

# ── pull ────────────────────────────────────────────────────────────────────
# refresh_images is study's pull helper: it pulls exactly when a registry
# pin is in play (STUDY_IMAGE, exported above) and never tries to build.
if [ "$NO_PULL" -eq 0 ]; then
    echo -e "${GREEN}Pulling the pinned images...${NC}"
    if ! refresh_images; then
        echo -e "${RED}Image pull failed (offline host? registry auth?).${NC}" >&2
        echo "  Re-run with --no-pull to reuse local images, or fix the network/credentials." >&2
        exit 2
    fi
elif [ -n "$IMAGE_PIN" ] && ! docker image inspect "$IMAGE_PIN" >/dev/null 2>&1; then
    echo -e "${YELLOW}--no-pull: ${IMAGE_PIN} is not present locally — 'up' cannot fall back to building (a bundle has no source). Drop --no-pull to pull it first.${NC}"
fi

# ── start ────────────────────────────────────────────────────────────────────
# One-time ADR-0022 DB/role rename (neuro_* → neuronection_*), before the
# stack boots against the new names. No-op on fresh installs.
migrate_legacy_db_names

echo -e "${GREEN}Starting the standalone stack...${NC}"
# up_stack is study's start helper: `up -d --no-build` under a pin (a
# source-free bundle has nothing to build).
if ! up_stack; then
    echo -e "${RED}docker compose up failed (exit above).${NC}" >&2
    report_compose_failure
    exit 3
fi

# ── health wait ──────────────────────────────────────────────────────────────
if [ "$NO_WAIT" -eq 0 ]; then
    wait_for_backend_healthy || exit 3
fi

# ── summary (URL, setup, backup, update, rollback) ───────────────────────────
SHORT_PIN="${IMAGE_PIN}"
if [ -n "$IMAGE_PIN" ]; then
    case "$IMAGE_PIN" in
        *@sha256:*) SHORT_PIN="${IMAGE_PIN%%@*}@${IMAGE_PIN##*@sha256:}" ;;
    esac
fi
HOST_HINT="$(hostname 2>/dev/null || echo localhost)"

echo
echo -e "${GREEN}======================================================${NC}"
echo -e "${GREEN}   Study Assistant is running!${NC}"
echo -e "${GREEN}======================================================${NC}"
echo "  Install:  ${INSTALL_DIR}"
[ -n "$MANIFEST_VERSION" ] && echo "  Version:  ${MANIFEST_VERSION}"
echo "  Image:    ${SHORT_PIN:-unpinned}"
PUBLIC_URL="$(env_value SA_PUBLIC_URL '')"
if [ -n "$PUBLIC_URL" ]; then
    echo "  URL:      ${PUBLIC_URL}   (SA_PUBLIC_URL — the address cookies/CORS accept)"
else
    echo "  URL:      http://${HOST_HINT}:${HTTP_PORT}   (or http://<your-host>:${HTTP_PORT})"
fi
echo "  Bind:     ${HTTP_BIND}:${HTTP_PORT} → container :80"
echo "  Health:   ${HEALTH_URL}"
# readyPath null = /ready not shipped at this release — no line, no probe.
[ -n "$READY_PATH" ] && echo "  Ready:    http://127.0.0.1:${HTTP_PORT}${READY_PATH}"
echo "  Setup:    ${SETUP_HINT}"
echo "  Docs:     ${DOCS_URL}"
echo
echo -e "${YELLOW}Next steps:${NC}"
echo "  * Backups: bash scripts/backup.sh (off-host: SA_BACKUP_RCLONE_REMOTE / SA_BACKUP_S3_URI /"
echo "    SA_BACKUP_AZURE_URL in ${ENV_FILE}; SA_BACKUP_AGE_RECIPIENT encrypts the archive)"
echo "  * Updates: extract the new release bundle over ${INSTALL_DIR}, then bash scripts/update.sh"
echo "  * Rollback: the previous pin is kept by update.sh; data restores via scripts/restore.sh"
