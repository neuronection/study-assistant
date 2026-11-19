#!/usr/bin/env bash
# Build the source-free deployment bundle for Study Assistant releases:
#
#   study-compose-v<version>.tar.gz   docker/ runtime + scripts/{install,update,
#                                     backup,restore,lib-docker}.sh + installer.json
#   manifest.json                     schemaVersion 2: product,
#                                     version/tag/commit, contractVersion,
#                                     images.app digest, bundle sha/bytes and
#                                     per-file sha256sums
#   SHA256SUMS                        checksums for the release-dir assets
#                                     (bundle + manifest; the release workflow
#                                     appends the bootstrap assets when the
#                                     generated scripts/bootstrap.sh is present)
#
# The bundle shape mirrors cloud-deploy's build-product-release.sh artifact
# (product=study): only the docker/ runtime (compose files, nginx configs,
# env example, entrypoint/init-db/backup helpers — init-db.sh is study's
# first-boot role bootstrap, mounted into /docker-entrypoint-initdb.d), the
# host scripts (installer, updater, backup/restore, lib) and installer.json
# — the product config the generated bootstrap and the website share. No
# source tree, no generated .env, no secrets. The application image is
# pinned separately by digest — the manifest records it; the compose files
# reference it via STUDY_IMAGE at deploy time and scripts/install.sh writes
# that pin.
#
# The image must already be pushed; this script never builds, logs in or
# uploads.
#
# Usage:
#   ./scripts/build-deploy-bundle.sh --version v0.14.0 \
#     --image ghcr.io/neuronection/study-assistant@sha256:<digest> \
#     [--out-dir dist]
#
# --version defaults to the exact tag on the current HEAD (git describe).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PRODUCT="study"
CONTRACT_VERSION="1"
VERSION="${VERSION:-}"
IMAGE=""
OUT_DIR="dist"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --version) VERSION="${2:?}"; shift ;;
    --image) IMAGE="${2:?}"; shift ;;
    --out-dir) OUT_DIR="${2:?}"; shift ;;
    -h|--help) sed -n '2,/^[^#]/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

if [ -z "$VERSION" ]; then
  VERSION="$(git -C "$ROOT" describe --tags --exact-match 2>/dev/null || true)"
fi
case "$VERSION" in
  v[0-9]*.[0-9]*.[0-9]*) ;;
  *) echo "--version must look like vX.Y.Z (got: ${VERSION:-<none>})" >&2; exit 2 ;;
esac
# Study keeps its strict digest validation: exactly 64 hex chars after
# @sha256: (career accepts a looser glob — this is a deliberate divergence).
case "$IMAGE" in
  *@sha256:[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]*) ;;
  *) echo "--image must be registry/repo@sha256:<64-hex digest> (got: ${IMAGE:-<none>})" >&2; exit 2 ;;
esac
if ! printf '%s' "$IMAGE" | grep -Eq '^[^@[:space:]]+@sha256:[0-9a-f]{64}$'; then
  echo "--image must be registry/repo@sha256:<64-hex digest> (got: ${IMAGE:-<none>})" >&2
  exit 2
fi
[ -d "$ROOT/docker" ] || { echo "not a study checkout (missing docker/): $ROOT" >&2; exit 1; }

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/docker" "$STAGE/scripts"
for file in docker-compose.prod.yml docker-compose.standalone.yml docker-compose.cloud.yml \
  nginx.conf nginx-TLS.conf entrypoint.sh init-db.sh backup-sidecar.sh README.md; do
  if [ -f "$ROOT/docker/$file" ]; then
    cp "$ROOT/docker/$file" "$STAGE/docker/"
  else
    echo "missing expected docker/$file" >&2
    exit 1
  fi
done
for env in docker/.env.production.example .env.production.example .env.example; do
  if [ -f "$ROOT/$env" ]; then
    cp "$ROOT/$env" "$STAGE/docker/.env.production.example"
    break
  fi
done
[ -f "$STAGE/docker/.env.production.example" ] || {
  echo "no env example found (docker/.env.production.example)" >&2
  exit 1
}
# Bundle-owned installer surface: the installer and updater run from the
# extracted bundle; backup/restore/lib-docker stay for the host.
for file in install.sh update.sh backup.sh restore.sh lib-docker.sh; do
  if [ -f "$ROOT/scripts/$file" ]; then
    cp "$ROOT/scripts/$file" "$STAGE/scripts/"
  else
    echo "missing expected scripts/$file" >&2
    exit 1
  fi
done
# Product config for the generated bootstrap + website (the canonical copy
# lives in the family installer contract; this repo ships it as
# installer.json).
if [ -f "$ROOT/installer.json" ]; then
  cp "$ROOT/installer.json" "$STAGE/installer.json"
else
  echo "missing expected installer.json" >&2
  exit 1
fi

# The bundle is intentionally source-free and secret-free: refuse any
# generated env file (only the checked-in example may ship).
if find "$STAGE" -type f \( -name '.env' -o -name '.env.*' \) ! -name '.env.production.example' | grep -q .; then
  echo "refusing bundle: generated .env file found" >&2
  exit 1
fi
if find "$STAGE" -type f \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' -o -name '*.mjs' \) | grep -q .; then
  echo "refusing bundle: source tree file found" >&2
  exit 1
fi

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
BUNDLE="$OUT_DIR/${PRODUCT}-compose-${VERSION}.tar.gz"
tar -C "$STAGE" -czf "$BUNDLE" .
BUNDLE_SHA="$(sha256sum "$BUNDLE" | awk '{print $1}')"
BUNDLE_BYTES="$(wc -c < "$BUNDLE" | tr -d ' ')"

COMMIT="$(git -C "$ROOT" rev-parse HEAD)"
TAG_COMMIT="$(git -C "$ROOT" rev-parse -q --verify "refs/tags/${VERSION}^{}" 2>/dev/null || true)"
if [ -n "$TAG_COMMIT" ] && [ "$TAG_COMMIT" != "$COMMIT" ]; then
  echo "product HEAD $COMMIT does not match $VERSION ($TAG_COMMIT)" >&2
  exit 1
fi

# Per-file sha256sums of the bundle contents, relative to the bundle root
# (the bootstrap can verify every file after extraction).
SHA_LINES=""
while IFS= read -r -d '' file; do
  rel="${file#"$STAGE"/}"
  sha="$(sha256sum "$file" | awk '{print $1}')"
  if [ -n "$SHA_LINES" ]; then SHA_LINES="${SHA_LINES},\n"; fi
  SHA_LINES="${SHA_LINES}    \"${rel}\": \"${sha}\""
done < <(find "$STAGE" -type f -print0 | sort -z)

cat > "$OUT_DIR/manifest.json" <<JSON
{
  "schemaVersion": 2,
  "product": "$PRODUCT",
  "version": "${VERSION#v}",
  "tag": "$VERSION",
  "commit": "$COMMIT",
  "contractVersion": "$CONTRACT_VERSION",
  "images": {
    "app": "$IMAGE"
  },
  "bundle": {
    "file": "$(basename "$BUNDLE")",
    "sha256": "$BUNDLE_SHA",
    "bytes": $BUNDLE_BYTES
  },
  "sha256sums": {
$(printf '%b' "$SHA_LINES")
  }
}
JSON
(
  cd "$OUT_DIR"
  sha256sum "$(basename "$BUNDLE")" manifest.json > SHA256SUMS
)

echo "deploy bundle: $BUNDLE"
echo "manifest + SHA256SUMS: $OUT_DIR"
cat "$OUT_DIR/manifest.json"
