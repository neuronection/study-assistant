#!/usr/bin/env bash
# Build the source-free deployment bundle for Study Assistant releases:
#
#   study-compose-v<version>.tar.gz   docker/ runtime + host backup/restore helpers
#   manifest.json                     product/version/commit/image digest/bundle SHA
#   SHA256SUMS                        checksums for the bundle + manifest
#
# The bundle shape mirrors cloud-deploy's build-product-release.sh artifact
# (product=study): only the docker/ runtime (compose files, nginx configs,
# env example, entrypoint/init/backup helpers) and the host backup/restore
# helpers. No source tree, no generated .env, no secrets. The application
# image is pinned separately by digest — the manifest records it; the
# compose files reference it via STUDY_IMAGE at deploy time.
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
VERSION="${VERSION:-}"
IMAGE=""
OUT_DIR="dist"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --version) VERSION="${2:?}"; shift ;;
    --image) IMAGE="${2:?}"; shift ;;
    --out-dir) OUT_DIR="${2:?}"; shift ;;
    -h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
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
for file in backup.sh restore.sh lib-docker.sh; do
  if [ -f "$ROOT/scripts/$file" ]; then
    cp "$ROOT/scripts/$file" "$STAGE/scripts/"
  else
    echo "missing expected scripts/$file" >&2
    exit 1
  fi
done

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

COMMIT="$(git -C "$ROOT" rev-parse HEAD)"
TAG_COMMIT="$(git -C "$ROOT" rev-parse -q --verify "refs/tags/${VERSION}^{}" 2>/dev/null || true)"
if [ -n "$TAG_COMMIT" ] && [ "$TAG_COMMIT" != "$COMMIT" ]; then
  echo "product HEAD $COMMIT does not match $VERSION ($TAG_COMMIT)" >&2
  exit 1
fi

cat > "$OUT_DIR/manifest.json" <<JSON
{
  "schemaVersion": 1,
  "product": "$PRODUCT",
  "version": "$VERSION",
  "commit": "$COMMIT",
  "image": "$IMAGE",
  "composeBundle": "$(basename "$BUNDLE")",
  "composeBundleSha256": "$BUNDLE_SHA",
  "contents": ["docker/ compose + nginx + env example", "host backup/restore helpers"]
}
JSON
(
  cd "$OUT_DIR"
  sha256sum "$(basename "$BUNDLE")" manifest.json > SHA256SUMS
)

echo "deploy bundle: $BUNDLE"
echo "manifest + SHA256SUMS: $OUT_DIR"
cat "$OUT_DIR/manifest.json"
