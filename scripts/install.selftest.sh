#!/usr/bin/env bash

# Study Assistant — installer self-test (the family installer contract wall)
#
# Exercises scripts/install.sh, scripts/update.sh and
# scripts/build-deploy-bundle.sh against a fake `docker` (no daemon, no
# images, no network) and a fake `curl`, plus a real bound socket for the
# port-conflict cases. Covers the contract flags, the image pin sources
# (manifest / --image-tag / $STUDY_IMAGE), the :latest refusal, the
# release-skew guard, the image assert, the port pre-flight, --auto-ports,
# --reset, the /api/v1/health wait failure reporting, study's docker/.env →
# root .env fallback, study's refresh_images / up_stack --no-build start
# pair and the bundle/manifest v2 shape (including docker/init-db.sh). No
# case needs real Docker, a registry or a network.
#
# Usage:
#   bash scripts/install.selftest.sh          # run every case
#   bash scripts/install.selftest.sh -v       # also print each command's output
#
# Exit: 0 all cases pass, 1 at least one failed.

set -u

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
VERBOSE=0
[ "${1:-}" = "-v" ] && VERBOSE=1

command -v python3 >/dev/null 2>&1 || { echo "python3 is required for the selftest" >&2; exit 1; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE="$(cd "$HERE/.." && pwd)"
PASS=0
FAIL=0
FAILED_CASES=""

WORK="$(mktemp -d)"
BG_PIDS=""
cleanup() {
    local pid
    for pid in $BG_PIDS; do kill "$pid" 2>/dev/null || true; done
    rm -rf "$WORK"
}
trap cleanup EXIT

say() { printf '%s\n' "$*"; }
ok()  { PASS=$((PASS + 1)); printf "${GREEN}  ok${NC}   %s\n" "$1"; }
bad() { FAIL=$((FAIL + 1)); FAILED_CASES="${FAILED_CASES}${1}"$'\n'; printf "${RED}  FAIL${NC} %s\n" "$1"; }

assert_contains() { # LABEL HAYSTACK NEEDLE
    case "$2" in
        *"$3"*) ok "$1" ;;
        *) bad "$1 (missing: $3)"; printf '%s\n' "$2" | sed 's/^/       | /' | tail -n 25 ;;
    esac
}
assert_not_contains() { # LABEL HAYSTACK NEEDLE
    case "$2" in
        *"$3"*) bad "$1 (unexpected: $3)"; printf '%s\n' "$2" | sed 's/^/       | /' | tail -n 25 ;;
        *) ok "$1" ;;
    esac
}
assert_eq() {
    if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (want '$3', got '$2')"; fi
}

# ── fake docker ─────────────────────────────────────────────────────────────
# Answers exactly what the scripts ask, from fixtures in $DOCKER_FIXTURES,
# and records every call (used to assert "nothing was pulled or started").
mkdir -p "$WORK/bin"
cat > "$WORK/bin/docker" <<'SHIM'
#!/usr/bin/env python3
import os, sys

args = sys.argv[1:]
fixtures = os.environ.get("DOCKER_FIXTURES", ".")

if os.environ.get("DOCKER_CALLS"):
    with open(os.environ["DOCKER_CALLS"], "a") as fh:
        fh.write(" ".join(args) + "\n")

def fx(name):
    path = os.path.join(fixtures, name)
    if os.path.exists(path):
        with open(path) as fh:
            return fh.read()
    return ""

if args[:1] == ["info"]:
    sys.exit(0)

if "version" in args and "compose" in args and "config" not in args:
    sys.stdout.write("Docker Compose version v2.31.0\n")
    sys.exit(0)

if "config" in args and "--format" in args:
    sys.stdout.write(fx("compose.json"))
    sys.exit(0)

if "ps" in args and "--filter" in args:
    spec = args[args.index("--filter") + 1]
    if spec.startswith("publish="):
        port = spec.split("=", 1)[1]
        for line in fx("port_owners").splitlines():
            if "\t" not in line:
                continue
            owned, project = line.split("\t", 1)
            if owned == port:
                print(project)
        sys.exit(0)
    if spec.startswith("label="):
        sys.stdout.write(fx("ids"))
        sys.exit(0)

if "ps" in args:
    sys.stdout.write(fx("compose_ps") or "NAME                 STATUS\n")
    sys.exit(0)

if "exec" in args and "psql" in args:
    sql = args[-1]
    if sql.strip() == "select 1":
        print("1")
        sys.exit(0)
    # pg_database / pg_roles lookups (and any DDL): no legacy names exist
    # on the fixture host, so every lookup answers "not found".
    sys.exit(0)

if args[:1] == ["volume"]:
    if "rm" in args:
        sys.exit(0)
    if os.environ.get("DOCKER_VOLUME_EXISTS") == "1":
        sys.exit(0)
    sys.exit(1)

if args[:1] == ["image"]:
    sys.exit(0)

if "logs" in args:
    print("fixture: service log line")
    sys.exit(0)

sys.exit(0)
SHIM
chmod +x "$WORK/bin/docker"

# ── fake curl (health wait) ─────────────────────────────────────────────────
mkdir -p "$WORK/bin-curl"
cat > "$WORK/bin-curl/curl" <<'SHIM'
#!/usr/bin/env bash
if [ "${CURL_MODE:-ok}" = "fail" ]; then
    exit 1
fi
printf '{"status": "ok"}\n'
SHIM
chmod +x "$WORK/bin-curl/curl"

# ── fake id (root refusal) ──────────────────────────────────────────────────
mkdir -p "$WORK/bin-root"
cat > "$WORK/bin-root/id" <<'SHIM'
#!/usr/bin/env bash
echo 0
SHIM
chmod +x "$WORK/bin-root/id"

export PATH="$WORK/bin-curl:$WORK/bin:$PATH"

# ── sandbox ─────────────────────────────────────────────────────────────────
# A minimal extracted-bundle tree: the REAL install.sh/update.sh/lib-docker.sh
# (so the wall tests the shipped scripts), a compose file with the real port
# expression, the real env example, a release manifest, and the rendered
# compose model the fake docker serves.
PIN_DIGEST="ghcr.io/neuronection/study-assistant@sha256:000000000000000000000000000000000000000000000000000000000000c0ffee"
OLD_PIN="ghcr.io/neuronection/study-assistant@sha00000000000000000000000000000000000000000000000000000000000000ldp1n"
FREE_PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
BUSY_PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"

new_sandbox() { # name pin published-port
    local DIR="$WORK/$1"
    mkdir -p "$DIR/docker" "$DIR/scripts" "$DIR/fixtures"
    cp "$CORE/scripts/install.sh" "$CORE/scripts/update.sh" "$CORE/scripts/lib-docker.sh" "$DIR/scripts/"
    cp "$CORE/installer.json" "$DIR/installer.json"
    cat > "$DIR/docker/docker-compose.standalone.yml" <<YAML
services:
  nginx:
    image: nginx:1.31.8-alpine
    ports:
      - "\${HTTP_PORT:-$3}:80"
YAML
    cp "$CORE/docker/.env.production.example" "$DIR/docker/.env.production.example"
    printf '{\n  "schemaVersion": 2,\n  "product": "study",\n  "version": "0.13.1",\n  "tag": "v0.13.1",\n  "contractVersion": "1",\n  "images": { "app": "%s" }\n}\n' "$2" > "$DIR/manifest.json"
    printf '{"name": "study-assistant", "services": {\n  "db": {"image": "pgvector/pgvector:0.8.7-pg16"},\n  "nginx": {"image": "nginx:1.31.8-alpine", "ports": [{"published": "%s", "target": 80}]},\n  "app": {"image": "%s"},\n  "migrate": {"image": "%s"}\n}}\n' "$3" "$2" "$2" > "$DIR/fixtures/compose.json"
    : > "$DIR/fixtures/port_owners"
    : > "$DIR/fixtures/compose_ps"
    : > "$DIR/fixtures/ids"
    printf '%s' "$DIR"
}

# installer.json must match the contract schema shape (installer.schema.json:
# required keys, additionalProperties:false, the study values the family
# contract pins — healthPath /api/v1/health, readyPath null, phase P3).
check_installer_shape() { # file
    python3 - "$1" <<'PY'
import json, sys
required = ["product", "title", "repo", "repoDir", "targetPath", "phase",
            "bundlePrefix", "bootstrapAsset", "envPrefix", "imageEnv",
            "imageKeys", "defaultDirName", "defaultPort", "healthPath",
            "readyPath", "setupMode", "minRamGb", "docsUrl", "installUrl",
            "contractVersion", "installFlags", "cookiePrefix"]
cfg = json.load(open(sys.argv[1]))
missing = [k for k in required if k not in cfg]
extra = [k for k in cfg if k not in required]
assert not missing, "missing required keys: %s" % missing
assert not extra, "extra keys rejected by additionalProperties:false: %s" % extra
assert cfg["product"] == "study", cfg["product"]
assert cfg["repo"] == "neuronection/study-assistant"
assert cfg["targetPath"] == "scripts/bootstrap.sh"
assert cfg["phase"] == "P3", cfg["phase"]
assert cfg["bundlePrefix"] == "study-compose", cfg["bundlePrefix"]
assert cfg["bootstrapAsset"] == "study-bootstrap", cfg["bootstrapAsset"]
assert cfg["envPrefix"] == "STUDY", cfg["envPrefix"]
assert cfg["imageEnv"] == "STUDY_IMAGE"
assert cfg["imageKeys"] == ["app"], cfg["imageKeys"]
assert cfg["readyPath"] is None, "study ships no /ready yet (its T1 conformance adds it)"
assert cfg["setupMode"] == "first user = admin", cfg["setupMode"]
assert cfg["defaultPort"] == 8091, cfg["defaultPort"]  # family default (8090/8091/8092)
assert cfg["healthPath"] == "/api/v1/health", "study's health endpoint is /api/v1/health"
assert cfg["docsUrl"] == "https://neuronection.com/docs/study", cfg["docsUrl"]
assert cfg["installUrl"] == "https://neuronection.com/install/study.sh", cfg["installUrl"]
assert cfg["contractVersion"] == "1"
flags = set(cfg["installFlags"])
need = {"no-pull", "no-wait", "auto-ports", "no-ports", "http-port", "public-url", "bind",
        "env-only", "reset", "yes", "image-tag"}
assert need <= flags, "installFlags missing: %s" % (need - flags)
assert "no-token" not in flags
assert cfg["cookiePrefix"] == "sa_", cfg["cookiePrefix"]
print("installer.json schema shape OK")
PY
}

seed_env() { # sandbox-dir pin port — an existing operator docker/.env
    cat > "$1/docker/.env" <<ENV
SA_SESSION_KEY=marker-session-secret-keep-me
SA_REFRESH_KEY=marker-refresh-secret-keep-me
SA_DATA_KEY=marker-data-secret-keep-me
SA_DB_OWNER_PASSWORD=marker-owner-pw
SA_DB_PASSWORD=marker-app-pw
STUDY_IMAGE=$2
HTTP_PORT=$3
ENV
}

run_docker_script() { # sandbox script args...
    local DIR="$1" SCRIPT="$2"; shift 2
    CASE_OUT="$(cd "$DIR" && env \
        PATH="${TEST_PATH:+$TEST_PATH:}$PATH" \
        DOCKER_FIXTURES="$DIR/fixtures" DOCKER_CALLS="$DIR/calls" \
        HEALTH_WAIT_INTERVAL=1 HEALTH_WAIT_ATTEMPTS=2 \
        CURL_MODE="${CURL_MODE:-ok}" \
        bash "$CORE/scripts/$SCRIPT" "$@" < /dev/null 2>&1)"
    RUN_STATUS=$?
    RUN_CALLS="$(cat "$DIR/calls" 2>/dev/null || true)"
    : > "$DIR/calls"
    [ "$VERBOSE" -eq 1 ] && printf '%s\n' "$CASE_OUT"
    return 0
}

start_listener() { # port
    python3 - "$1" <<'PY' &
import socket, sys, time
srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", int(sys.argv[1])))
srv.listen(4)
time.sleep(120)
PY
    BG_PIDS="$BG_PIDS $!"
    local i=0
    while [ "$i" -lt 40 ]; do
        if python3 -c "import socket,sys
s=socket.socket(); s.settimeout(0.2)
sys.exit(0 if s.connect_ex(('127.0.0.1', int('$1'))) == 0 else 1)"; then
            return 0
        fi
        sleep 0.1
        i=$((i + 1))
    done
    return 1
}

stop_listeners() {
    local pid
    for pid in $BG_PIDS; do kill "$pid" 2>/dev/null || true; done
    BG_PIDS=""
    sleep 0.2
}

# ── help and usage ───────────────────────────────────────────────────────────
say "${YELLOW}install.sh: --help and unknown flags${NC}"
SB="$(new_sandbox help "$PIN_DIGEST" "$FREE_PORT")"
run_docker_script "$SB" install.sh --help
assert_eq "--help exits 0" "$RUN_STATUS" "0"
assert_contains "help names --image-tag" "$CASE_OUT" "--image-tag"
assert_contains "help names --http-port" "$CASE_OUT" "--http-port"
assert_contains "help names the exit codes" "$CASE_OUT" "4 port conflict"
assert_not_contains "--help performs no install" "$RUN_CALLS" "up -d"

run_docker_script "$SB" install.sh --bogus-flag
assert_eq "unknown flag exits 1" "$RUN_STATUS" "1"
assert_contains "unknown flag points at --help" "$CASE_OUT" "try --help"

say "${YELLOW}install.sh: refuses root${NC}"
TEST_PATH="$WORK/bin-root"
run_docker_script "$SB" install.sh --env-only
TEST_PATH=""
assert_eq "root exits 1" "$RUN_STATUS" "1"
assert_contains "root refusal names the fix" "$CASE_OUT" "Refusing to run as root"
assert_not_contains "root refusal starts nothing" "$RUN_CALLS" "up -d"

# ── installer.json is the canonical config ────────────────────────────────────
say "${YELLOW}installer.json: canonical contract config${NC}"
if check_installer_shape "$CORE/installer.json" >/dev/null 2>&1; then
    ok "repo installer.json matches the schema shape"
else
    bad "repo installer.json matches the schema shape"
    check_installer_shape "$CORE/installer.json" 2>&1 | sed 's/^/       | /' | head -5
fi

# ── image pin sources ────────────────────────────────────────────────────────
say "${YELLOW}install.sh: image pin sources${NC}"
SB="$(new_sandbox pin-manifest "$PIN_DIGEST" "$FREE_PORT")"
run_docker_script "$SB" install.sh --env-only
assert_eq "--env-only with manifest exits 0" "$RUN_STATUS" "0"
assert_contains "manifest digest pinned" "$(grep '^STUDY_IMAGE=' "$SB/docker/.env")" "STUDY_IMAGE=$PIN_DIGEST"
assert_not_contains "--env-only pulls nothing" "$RUN_CALLS" " pull"
assert_not_contains "--env-only starts nothing" "$RUN_CALLS" " up -d"
assert_eq ".env is 0600" "$(stat -c %a "$SB/docker/.env")" "600"
if grep -qE 'replace-with-generated|^SA_DB_OWNER_PASSWORD=change-me|^SA_DB_PASSWORD=change-me$' "$SB/docker/.env"; then
    bad "placeholders were replaced by generated secrets"
else
    ok "placeholders were replaced by generated secrets"
fi
SK1="$(grep '^SA_SESSION_KEY=' "$SB/docker/.env" | cut -d= -f2-)"
SK2="$(grep '^SA_REFRESH_KEY=' "$SB/docker/.env" | cut -d= -f2-)"
SK3="$(grep '^SA_DATA_KEY=' "$SB/docker/.env" | cut -d= -f2-)"
if [ "$SK1" != "$SK2" ] && [ "$SK2" != "$SK3" ]; then
    ok "the three key-family secrets are independent"
else
    bad "the three key-family secrets are independent"
fi
assert_not_contains "secrets are not printed" "$CASE_OUT" "$SK1"
assert_not_contains "secrets are not printed (data key)" "$CASE_OUT" "$SK3"

SB="$(new_sandbox pin-keyref "$PIN_DIGEST" "$FREE_PORT")"
run_docker_script "$SB" install.sh --env-only --image "app=$PIN_DIGEST"
assert_eq "--image KEY=REF (the bootstrap hand-off form) exits 0" "$RUN_STATUS" "0"
assert_contains "KEY=REF pin lands in docker/.env" "$(grep '^STUDY_IMAGE=' "$SB/docker/.env")" "STUDY_IMAGE=$PIN_DIGEST"

SB="$(new_sandbox pin-rogue "$PIN_DIGEST" "$FREE_PORT")"
run_docker_script "$SB" install.sh --env-only --image "rogue=$PIN_DIGEST"
assert_eq "a foreign image key exits 1" "$RUN_STATUS" "1"
assert_contains "foreign key names imageKeys" "$CASE_OUT" "unknown image key 'rogue'"

SB="$(new_sandbox pin-tag "$PIN_DIGEST" "$FREE_PORT")"
run_docker_script "$SB" install.sh --env-only --image-tag v0.13.1
assert_eq "--image-tag exits 0" "$RUN_STATUS" "0"
assert_contains "tag resolves via the manifest repo" "$(grep '^STUDY_IMAGE=' "$SB/docker/.env")" "STUDY_IMAGE=ghcr.io/neuronection/study-assistant:0.13.1"

SB="$(new_sandbox pin-env "$PIN_DIGEST" "$FREE_PORT")"
rm "$SB/manifest.json"
CASE_OUT="$(cd "$SB" && STUDY_IMAGE="$PIN_DIGEST" bash "$CORE/scripts/install.sh" --env-only 2>&1)"
assert_eq "STUDY_IMAGE env pins" "$?" "0"
assert_contains "env pin lands in docker/.env" "$(grep '^STUDY_IMAGE=' "$SB/docker/.env")" "STUDY_IMAGE=$PIN_DIGEST"

SB="$(new_sandbox pin-latest "$PIN_DIGEST" "$FREE_PORT")"
run_docker_script "$SB" install.sh --env-only --image "ghcr.io/neuronection/study-assistant:latest"
assert_eq "operator-typed :latest is refused" "$RUN_STATUS" "1"
assert_contains ":latest refusal cites the rule" "$CASE_OUT" "Refusing the mutable pin"
if [ -f "$SB/docker/.env" ]; then
    bad "refusal happens before .env is written"
else
    ok "refusal happens before .env is written"
fi

SB="$(new_sandbox pin-skew "$PIN_DIGEST" "$FREE_PORT")"
run_docker_script "$SB" install.sh --env-only --image-tag 0.14.0
assert_eq "tag skewing from the manifest exits 1" "$RUN_STATUS" "1"
assert_contains "skew names the manifest version" "$CASE_OUT" "version 0.13.1"

SB="$(new_sandbox pin-none "$PIN_DIGEST" "$FREE_PORT")"
rm "$SB/manifest.json"
run_docker_script "$SB" install.sh
assert_eq "no pin exits 1" "$RUN_STATUS" "1"
assert_contains "no pin explains the bundle has no source" "$CASE_OUT" "No image pin"
assert_contains "no pin names the manifest fix" "$CASE_OUT" "manifest.json"
if [ -f "$SB/docker/.env" ]; then
    bad "no-pin failure writes no .env"
else
    ok "no-pin failure writes no .env"
fi

run_docker_script "$SB" install.sh --env-only
assert_eq "--env-only without a pin still writes .env" "$RUN_STATUS" "0"
assert_contains "--env-only warns about the missing pin" "$CASE_OUT" "no image pin"

# ── existing .env and re-run ──────────────────────────────────────────────────
say "${YELLOW}install.sh: existing docker/.env and re-run${NC}"
SB="$(new_sandbox exists "$OLD_PIN" "$FREE_PORT")"
rm "$SB/manifest.json"
seed_env "$SB" "$OLD_PIN" 8091
BEFORE_SHA="$(sha256sum "$SB/docker/.env" | awk '{print $1}')"
run_docker_script "$SB" install.sh --env-only
assert_eq "existing .env run exits 0" "$RUN_STATUS" "0"
assert_contains "existing .env is announced" "$CASE_OUT" "leaving it untouched"
assert_eq "existing .env is byte-identical" "$(sha256sum "$SB/docker/.env" | awk '{print $1}')" "$BEFORE_SHA"
assert_not_contains "existing .env run starts nothing" "$RUN_CALLS" "up -d"

# study's docker/.env → root .env fallback: an existing root .env is used
# where it is, announced, and never migrated or overwritten.
SB="$(new_sandbox exists-root "$OLD_PIN" "$FREE_PORT")"
rm "$SB/manifest.json"
cat > "$SB/.env" <<ENV
SA_SESSION_KEY=marker-session-secret-keep-me
SA_REFRESH_KEY=marker-refresh-secret-keep-me
SA_DATA_KEY=marker-data-secret-keep-me
SA_DB_OWNER_PASSWORD=marker-owner-pw
SA_DB_PASSWORD=marker-app-pw
STUDY_IMAGE=$OLD_PIN
HTTP_PORT=$FREE_PORT
ENV
BEFORE_SHA="$(sha256sum "$SB/.env" | awk '{print $1}')"
run_docker_script "$SB" install.sh --env-only
assert_eq "root .env fallback run exits 0" "$RUN_STATUS" "0"
assert_contains "root .env fallback is announced" "$CASE_OUT" "using root .env"
assert_contains "root .env is kept, not replaced" "$CASE_OUT" "leaving it untouched"
assert_eq "root .env is byte-identical" "$(sha256sum "$SB/.env" | awk '{print $1}')" "$BEFORE_SHA"
if [ -f "$SB/docker/.env" ]; then
    bad "root .env fallback creates no docker/.env"
else
    ok "root .env fallback creates no docker/.env"
fi

SB="$(new_sandbox rerun "$PIN_DIGEST" "$FREE_PORT")"
run_docker_script "$SB" install.sh --http-port "$FREE_PORT"
assert_eq "first install exits 0" "$RUN_STATUS" "0"
assert_contains "health wait passes" "$CASE_OUT" "App is healthy"
assert_contains "health wait hits /api/v1/health" "$CASE_OUT" "/api/v1/health"
assert_contains "summary names the URL" "$CASE_OUT" ":$FREE_PORT"
assert_contains "summary names the image pin" "$CASE_OUT" "$PIN_DIGEST"
assert_contains "first-admin setup note" "$CASE_OUT" "first user becomes the admin"
assert_not_contains "no Ready line (study readyPath is null)" "$CASE_OUT" "Ready:"
assert_contains "summary links the canonical docs" "$CASE_OUT" "https://neuronection.com/docs/study"
assert_contains "stack starts with study's up_stack --no-build" "$RUN_CALLS" "up -d --no-build"
ENV_SHA="$(sha256sum "$SB/docker/.env" | awk '{print $1}')"
run_docker_script "$SB" install.sh
assert_eq "re-run exits 0" "$RUN_STATUS" "0"
assert_contains "re-run keeps docker/.env" "$CASE_OUT" "leaving it untouched"
assert_eq "re-run does not rewrite docker/.env" "$(sha256sum "$SB/docker/.env" | awk '{print $1}')" "$ENV_SHA"
assert_contains "re-run still refreshes the stack (study's --no-build pair)" "$RUN_CALLS" "up -d --no-build"
assert_contains "re-run still pulls" "$RUN_CALLS" " pull"

# ── port pre-flight ───────────────────────────────────────────────────────────
say "${YELLOW}install.sh: port pre-flight${NC}"
start_listener "$BUSY_PORT" || bad "could not bind the busy test port"
SB="$(new_sandbox ports-busy "$PIN_DIGEST" "$BUSY_PORT")"
run_docker_script "$SB" install.sh --http-port "$BUSY_PORT"
assert_eq "busy port exits 4" "$RUN_STATUS" "4"
assert_contains "busy port names the .env knob" "$CASE_OUT" "HTTP_PORT"
assert_contains "busy port names the port" "$CASE_OUT" "$BUSY_PORT"
assert_not_contains "busy port aborts before pulling" "$RUN_CALLS" " pull"
assert_not_contains "busy port aborts before starting" "$RUN_CALLS" " up"

SB="$(new_sandbox ports-ours "$PIN_DIGEST" "$BUSY_PORT")"
printf '%s\tstudy-assistant\n' "$BUSY_PORT" > "$SB/fixtures/port_owners"
run_docker_script "$SB" install.sh --http-port "$BUSY_PORT"
assert_eq "our own project's port is not a conflict" "$RUN_STATUS" "0"
stop_listeners

start_listener "$BUSY_PORT" || bad "could not bind the busy test port"
SB="$(new_sandbox ports-auto "$PIN_DIGEST" "$BUSY_PORT")"
run_docker_script "$SB" install.sh --http-port "$BUSY_PORT" --auto-ports
assert_eq "--auto-ports exits 0" "$RUN_STATUS" "0"
assert_contains "--auto-ports reports the move (fixtures needle)" "$CASE_OUT" "written to .env"
AUTO_PORT="$(grep '^HTTP_PORT=' "$SB/docker/.env" | cut -d= -f2)"
if [ -n "$AUTO_PORT" ] && [ "$AUTO_PORT" != "$BUSY_PORT" ]; then
    ok "--auto-ports picked a different port ($AUTO_PORT)"
else
    bad "--auto-ports kept the busy port"
fi
assert_contains "--auto-ports still starts the stack" "$RUN_CALLS" "up -d"

SB="$(new_sandbox ports-skip "$PIN_DIGEST" "$BUSY_PORT")"
run_docker_script "$SB" install.sh --http-port "$BUSY_PORT" --no-ports
assert_eq "--no-ports skips the conflict check" "$RUN_STATUS" "0"
assert_contains "--no-ports starts the stack" "$RUN_CALLS" "up -d"
stop_listeners

# ── image verification ────────────────────────────────────────────────────────
say "${YELLOW}install.sh: image verification${NC}"
SB="$(new_sandbox assert-bad "$PIN_DIGEST" "$FREE_PORT")"
# render a compose model that disagrees with the manifest pin
python3 - "$SB/fixtures/compose.json" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path))
bad = "ghcr.io/neuronection/study-assistant@sha256:" + "b" * 64
for name in ("app", "migrate"):
    data["services"][name]["image"] = bad
json.dump(data, open(path, "w"))
PY
run_docker_script "$SB" install.sh --http-port "$FREE_PORT"
assert_eq "rendered-image mismatch exits 3 (fixtures: manifest-image-compose-assert)" "$RUN_STATUS" "3"
assert_contains "mismatch names both refs" "$CASE_OUT" "Image verification failed"
assert_contains "mismatch cites the manifest" "$CASE_OUT" "manifest.json"
assert_not_contains "mismatch aborts before pulling" "$RUN_CALLS" " pull"
assert_not_contains "mismatch aborts before starting" "$RUN_CALLS" " up -d"

# A manifest-sourced mutable pin flows to the render wall (fixtures row
# mutable-compose-ref-refused): exit 3, latest named, nothing pulled/started.
SB="$(new_sandbox mutable-manifest "ghcr.io/neuronection/study-assistant:latest" "$FREE_PORT")"
run_docker_script "$SB" install.sh --http-port "$FREE_PORT"
assert_eq "manifest :latest pin exits 3 at the render wall" "$RUN_STATUS" "3"
assert_contains "the mutable ref is named" "$CASE_OUT" "latest"
assert_not_contains "mutable manifest aborts before pulling" "$RUN_CALLS" " pull"
assert_not_contains "mutable manifest aborts before starting" "$RUN_CALLS" " up -d"

# ── reset ────────────────────────────────────────────────────────────────────
say "${YELLOW}install.sh: --reset${NC}"
SB="$(new_sandbox reset "$PIN_DIGEST" "$FREE_PORT")"
run_docker_script "$SB" install.sh --http-port "$FREE_PORT" --reset
assert_eq "--reset without --yes refuses non-interactively" "$RUN_STATUS" "1"
assert_contains "--reset without --yes explains the flag" "$CASE_OUT" "--reset needs --yes"

DOCKER_VOLUME_EXISTS=1
export DOCKER_VOLUME_EXISTS
SB="$(new_sandbox reset-yes "$PIN_DIGEST" "$FREE_PORT")"
run_docker_script "$SB" install.sh --http-port "$FREE_PORT" --reset --yes
unset DOCKER_VOLUME_EXISTS
assert_eq "--reset --yes exits 0" "$RUN_STATUS" "0"
assert_contains "reset lists the db volume" "$CASE_OUT" "study-assistant_db_data"
assert_contains "reset lists the data volume" "$CASE_OUT" "study-assistant_data"
assert_contains "reset removes the volumes" "$RUN_CALLS" "volume rm"
assert_contains "reset warns about the leftover db volume" "$CASE_OUT" "previous install's database volume"

# ── health-wait failure reporting ────────────────────────────────────────────
say "${YELLOW}install.sh: health-wait failure reporting${NC}"
CURL_MODE=fail
SB="$(new_sandbox wait-fail "$PIN_DIGEST" "$FREE_PORT")"
run_docker_script "$SB" install.sh --http-port "$FREE_PORT"
assert_eq "failed health wait exits 3" "$RUN_STATUS" "3"
assert_contains "failure names the timeout" "$CASE_OUT" "did not become healthy"
assert_contains "failure prints the compose table" "$CASE_OUT" "Compose services"
assert_contains "failure tails migrate logs" "$CASE_OUT" "Last log lines — migrate"
CURL_MODE=ok

# ── update.sh ────────────────────────────────────────────────────────────────
say "${YELLOW}update.sh: pin bump, rollback pin, no destructive ops${NC}"
SB="$(new_sandbox update-bump "$PIN_DIGEST" "$FREE_PORT")"
seed_env "$SB" "$OLD_PIN" "$FREE_PORT"
run_docker_script "$SB" update.sh
assert_eq "update with new manifest exits 0" "$RUN_STATUS" "0"
assert_contains "pin moved to the manifest digest" "$(grep '^STUDY_IMAGE=' "$SB/docker/.env")" "STUDY_IMAGE=$PIN_DIGEST"
assert_contains "previous pin kept as a comment" "$(grep '# previous STUDY_IMAGE' "$SB/docker/.env")" "$OLD_PIN"
assert_contains "pin move is reported" "$CASE_OUT" "Image pin moved"
assert_contains "rollback command printed" "$CASE_OUT" "update.sh --image $OLD_PIN"
assert_contains "update pulls" "$RUN_CALLS" " pull"
assert_contains "update recreates the stack (study's --no-build pair)" "$RUN_CALLS" "up -d --no-build"
assert_not_contains "update removes no volumes" "$RUN_CALLS" "volume rm"

SB="$(new_sandbox update-keep "$OLD_PIN" "$FREE_PORT")"
rm "$SB/manifest.json"
seed_env "$SB" "$OLD_PIN" "$FREE_PORT"
run_docker_script "$SB" update.sh
assert_eq "update without a new pin exits 0" "$RUN_STATUS" "0"
assert_contains "current pin kept" "$CASE_OUT" "Keeping the current image pin"
assert_contains "pin unchanged in docker/.env" "$(grep '^STUDY_IMAGE=' "$SB/docker/.env")" "STUDY_IMAGE=$OLD_PIN"

SB="$(new_sandbox update-noenv "$PIN_DIGEST" "$FREE_PORT")"
rm "$SB/manifest.json"
run_docker_script "$SB" update.sh
assert_eq "update without an env file exits 1" "$RUN_STATUS" "1"
assert_contains "points at install.sh" "$CASE_OUT" "Run scripts/install.sh first"

# ── bundle builder (manifest v2 + bundle shape) ──────────────────────────────
say "${YELLOW}build-deploy-bundle.sh: source-free bundle, manifest v2${NC}"
BB="$WORK/bundle-repo"
mkdir -p "$BB/docker" "$BB/scripts"
for f in docker-compose.prod.yml docker-compose.standalone.yml docker-compose.cloud.yml \
    nginx.conf nginx-TLS.conf entrypoint.sh init-db.sh backup-sidecar.sh README.md .env.production.example; do
    cp "$CORE/docker/$f" "$BB/docker/$f"
done
for f in install.sh update.sh backup.sh restore.sh uninstall.sh lib-docker.sh build-deploy-bundle.sh; do
    cp "$CORE/scripts/$f" "$BB/scripts/$f"
done
cp "$CORE/installer.json" "$BB/installer.json"
git -C "$BB" init -q
git -C "$BB" add -A
git -C "$BB" -c user.email=selftest@localhost -c user.name=selftest commit -qm "selftest fixture"
BIMAGE="ghcr.io/neuronection/study-assistant@sha256:$(printf 'a%.0s' $(seq 1 64))"
if CASE_OUT="$(cd "$BB" && bash scripts/build-deploy-bundle.sh --version v9.9.9 --image "$BIMAGE" --out-dir dist 2>&1)"; then
    ok "bundle build exits 0"
else
    bad "bundle build exits 0"
    printf '%s\n' "$CASE_OUT" | sed 's/^/       | /' | tail -n 25
fi
assert_contains "manifest is schemaVersion 2" "$(cat "$BB/dist/manifest.json")" '"schemaVersion": 2'
assert_contains "manifest carries contractVersion" "$(cat "$BB/dist/manifest.json")" '"contractVersion": "1"'
assert_contains "manifest carries the passed digest" "$(cat "$BB/dist/manifest.json")" "\"app\": \"$BIMAGE\""
assert_contains "manifest carries the version pair" "$(cat "$BB/dist/manifest.json")" '"version": "9.9.9",'
assert_contains "manifest carries the tag" "$(cat "$BB/dist/manifest.json")" '"tag": "v9.9.9"'
TARLIST="$(tar -tzf "$BB/dist/study-compose-v9.9.9.tar.gz")"
assert_contains "bundle ships scripts/install.sh" "$TARLIST" "scripts/install.sh"
assert_contains "bundle ships scripts/update.sh" "$TARLIST" "scripts/update.sh"
assert_contains "bundle ships installer.json" "$TARLIST" "installer.json"
assert_contains "bundle ships backup helpers" "$TARLIST" "scripts/backup.sh"
assert_contains "bundle ships docker/init-db.sh (study's first-boot role bootstrap)" "$TARLIST" "docker/init-db.sh"
if printf '%s\n' "$TARLIST" | grep -qE '\.env$'; then
    bad "bundle ships no generated .env"
else
    ok "bundle ships no generated .env"
fi
assert_not_contains "bundle ships no source tree" "$TARLIST" ".py"
MBYTES="$(python3 -c "import json; print(json.load(open('$BB/dist/manifest.json'))['bundle']['bytes'])")"
ACTUAL_BYTES="$(wc -c < "$BB/dist/study-compose-v9.9.9.tar.gz" | tr -d ' ')"
assert_eq "manifest bundle.bytes matches" "$MBYTES" "$ACTUAL_BYTES"
MSHA="$(python3 -c "import json; print(json.load(open('$BB/dist/manifest.json'))['bundle']['sha256'])")"
assert_eq "manifest bundle.sha256 matches" "$MSHA" "$(sha256sum "$BB/dist/study-compose-v9.9.9.tar.gz" | awk '{print $1}')"
INNER_SHA="$(python3 -c "import json; print(json.load(open('$BB/dist/manifest.json'))['sha256sums']['scripts/install.sh'])")"
EXTRACT="$WORK/bundle-extract" && mkdir -p "$EXTRACT"
tar -xzf "$BB/dist/study-compose-v9.9.9.tar.gz" -C "$EXTRACT"
assert_eq "per-file sha256sums are real" "$INNER_SHA" "$(sha256sum "$EXTRACT/scripts/install.sh" | awk '{print $1}')"
if check_installer_shape "$EXTRACT/installer.json" >/dev/null 2>&1; then
    ok "the bundle ships the canonical installer.json"
else
    bad "the bundle ships the canonical installer.json"
    check_installer_shape "$EXTRACT/installer.json" 2>&1 | sed 's/^/       | /' | head -5
fi
VERIFIED="$(cd "$BB/dist" && sha256sum -c SHA256SUMS 2>&1)"
assert_contains "release SHA256SUMS verifies" "$VERIFIED" "OK"

# ── summary ──────────────────────────────────────────────────────────────────
say ""
if [ "$FAIL" -eq 0 ]; then
    printf "${GREEN}install self-test: %s passed${NC}\n" "$PASS"
    exit 0
fi
printf "${RED}install self-test: %s passed, %s FAILED${NC}\n" "$PASS" "$FAIL"
printf '%s' "$FAILED_CASES" | sed 's/^/  - /'
exit 1
