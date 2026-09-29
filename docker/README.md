# Study Assistant - Docker Utilities & Cheat Sheet

This directory contains the Docker configuration files for Study Assistant.
It mirrors Health and Career Assistant's docker layout (family standard,
deployment.md / ADR-0022): the **web stack runs PostgreSQL 16** (pgvector) —
desktop installs keep SQLite (`<data_dir>/study.sqlite3`), that convention
does not apply here.

For development on the host see `docs/` and `scripts/run-dev.sh`.

## File map

| File | Purpose |
|---|---|
| `docker-compose.dev-db.yml` | Dev infrastructure only: Postgres :5434 (`neuro_study` + `neuro_study_test`) for host-based development and tests (`scripts/run-dev.sh`). |
| `docker-compose.prod.yml` | Production services (db + app + backup). Proxy handled externally or via the standalone flavor. App bound to `127.0.0.1:${SA_PORT:-8200}`. Supports `STUDY_IMAGE` to deploy pre-built GHCR images. |
| `docker-compose.standalone.yml` | Canonical self-hosted single-host stack: **db + app + nginx + backup** (TLS-ready). |
| `docker-compose.demo.yml` | Demo flavor (S8): isolated compose project/network, `neuro_study_demo`, synthetic-only data seeded by `scripts/seed-demo.py`, SPA badged "Demo — synthetic data". Never production. |
| `Dockerfile` | Multi-stage: pnpm frontend bundle → single uvicorn image serving API + SPA. Builds with the named `auth-kit` build context (family auth-kit, an editable `../auth-kit` path dep in the root `pyproject.toml`/`uv.lock`). |
| `entrypoint.sh` | Demo guard → waits for the DB → runs migrations (owner role) → starts uvicorn. |
| `init-db.sh` | First-boot Postgres bootstrap: family roles + optional `neuro_study_test` (mounted into `/docker-entrypoint-initdb.d`). |
| `nginx.conf` | HTTP-only reverse proxy incl. the `/ws` WebSocket endpoint (loopback / VPN). |
| `nginx-TLS.conf` | TLS-terminating variant (certbot webroot ACME + HSTS). |
| `.env.production.example` | Template for `docker/.env` (the one required secret: `SA_DB_PASSWORD`). |

Ops scripts (repo `scripts/`): `run-docker.sh` (first deploy), `update-docker.sh`
(refresh), `lib-docker.sh` (shared helpers), `backup.sh` / `restore.sh`
(instance backup + restore, see the restore drill below).

## Databases & roles (ADR-0022)

Web mode runs **PostgreSQL 16** (`pgvector/pgvector` — embeddings use pgvector).
Naming and env vars follow deployment.md:

| Item | Value |
|---|---|
| Database | `neuro_study` (test: `neuro_study_test`) |
| Roles | `neuro_study_owner` (owns schema, runs migrations/DDL) + `neuro_study_app` (runtime, CONNECT + DML only — never DDL) |
| Env vars | `SA_DB_NAME`, `SA_DB_USER`, `SA_DB_PASSWORD`, `SA_DATABASE_URL` (**URL wins** when set); `SA_DB_HOST`/`SA_DB_PORT` for the non-URL form |

**Two-role split — what exactly happens here:** `docker/init-db.sh` creates
both roles on first boot of the data volume and grants the app role DML-only
privileges (plus `ALTER DEFAULT PRIVILEGES` so tables the owner creates during
migrations are covered automatically). The app container gets **two URLs**:
`SA_DATABASE_URL` connects as `neuro_study_app` (the runtime, least
privilege) and `SA_MIGRATIONS_DATABASE_URL` is used *only* by
`entrypoint.sh` to run `alembic upgrade head` as `neuro_study_owner` on
every boot — migrations are never a manual step. Both roles share the single
`SA_DB_PASSWORD`, so the env surface stays exactly at the law's four vars;
the split is privilege-based, not credential-based. Consequences: the app
container holds the owner password (it must, to auto-migrate), and the
runtime role can never alter the schema.

## Dev infrastructure (host-based development)

```bash
SA_DB_PASSWORD=study_dev_pw docker compose -f docker/docker-compose.dev-db.yml up -d
# → Postgres on 127.0.0.1:5434 (neuro_study + neuro_study_test)
./scripts/run-dev.sh                                        # backend :8200 + frontend :3200
```

- `SA_DB_PASSWORD` is `:?`-guarded (any dev-only value); the port knob is
  `SA_DB_PORT` (default **5434** — study's dev-infra port; see
  `dev/guidelines/dev-ports.md`).
- Container name `study-postgres` / project `study` are env-overridable
  (`SA_DB_CONTAINER`, `COMPOSE_PROJECT_NAME`, `SA_DB_PORT`) so git-worktree
  sessions can run side by side.
- Host-based dev connects with `SA_DB_HOST=localhost SA_DB_PORT=5434
  SA_DB_USER=neuro_study_owner SA_DB_PASSWORD=…` (or `SA_DATABASE_URL`).

## Self-hosting (standalone flavor)

```bash
cp docker/.env.production.example docker/.env   # then set SA_DB_PASSWORD
docker compose -f docker/docker-compose.standalone.yml up -d --build
# → http://localhost
```

- Stack: PostgreSQL 16 + app image (API + SPA same-origin) + nginx; the app
  entrypoint runs migrations automatically on every start.
- Required secret `SA_DB_PASSWORD` (URL-safe characters only) is `:?`-guarded —
  `up` fails loud and early without it.
- Optional scheduled backups (DB dump + data volume to `docker/backups/`):
  add `--profile backup` (`BACKUP_INTERVAL_HOURS` / `BACKUP_KEEP`).
- Deploy a pre-built image instead of building:
  `STUDY_IMAGE=ghcr.io/<owner>/<repo>:<tag> docker compose ... up -d`
  (images are published by the release workflow on tags).
- First deploy / refresh: `scripts/run-docker.sh` / `scripts/update-docker.sh`.
- **Build requirement:** building the image (as opposed to deploying a
  pre-built `STUDY_IMAGE`) needs the family **auth-kit** checkout as a sibling
  (`../auth-kit`) — the root `pyproject.toml`/`uv.lock` pin it as an editable
  path dep and the Dockerfile receives it as the named `auth-kit` build
  context (compose wires `build.additional_contexts`).

Persistent state: `db_data` volume (PostgreSQL) and `data` volume
(`SA_DATA_DIR=/data`: blobs, cache, thumbnails, import-inbox, in-app
backups). Desktop SQLite conventions (`study.sqlite3`) do not apply here.

## TLS

The default `nginx.conf` is HTTP-only — use it only behind a VPN or on
loopback. For internet-facing deployments:

1. Mount `nginx-TLS.conf` over `nginx.conf` (uncomment the commented volumes
   in the compose file, including `443:443`).
2. Provide certs at `docker/certs/fullchain.pem` + `privkey.pem`
   (certbot webroot renewals answer on port 80 via
   `/.well-known/acme-challenge/`).
3. Set `SERVER_NAME` in the conf to your domain.

## Backup & restore drill

Backup is a service, not a ritual: the `--profile backup` sidecar writes
timestamped `db-*.dump` (`pg_dump -Fc`) + `data-*.tar.gz` archives into
`docker/backups/` every `BACKUP_INTERVAL_HOURS`, keeping `BACKUP_KEEP` of
each. Host-side one-shots (used by the drill and for off-machine copies) are
`scripts/backup.sh` → `backups/study-assistant-<stamp>.tar.gz`
(manifest + `database.dump` + `data.tar.gz`) and `scripts/restore.sh`.

**Drill (run it before you rely on it):**

```bash
# 1. Seed data — start the stack and create something you can recognize.
cp docker/.env.production.example docker/.env   # set SA_DB_PASSWORD
scripts/run-docker.sh
curl -s -X POST http://localhost/api/v1/auth/register \
  -H 'Content-Type: application/json' -c /tmp/drill-jar \
  -d '{"email":"drill@example.com","password":"correct-horse-battery"}'   # → 201
CSRF="$(awk '$6=="nx_csrf" {print $7}' /tmp/drill-jar)"
PROFILE="$(curl -s -b /tmp/drill-jar http://localhost/api/v1/profiles \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')"
curl -s -X POST http://localhost/api/v1/courses -b /tmp/drill-jar \
  -H 'Content-Type: application/json' -H "X-CSRF-Token: $CSRF" \
  -H "X-Profile-Id: $PROFILE" \
  -d '{"title":"Restore Drill Course"}'   # → 201

# 2. Back up.
scripts/backup.sh                       # → backups/study-assistant-<stamp>.tar.gz

# 3. Destroy the data (--profile backup also stops the backup sidecar, which
#    otherwise keeps the volumes in use).
docker compose -f docker/docker-compose.standalone.yml --profile backup down -v

# 4. Restore (nothing is touched without --yes / FORCE=1). Stop the backup
#    sidecar first — otherwise its dump tick can race pg_restore and capture
#    a half-empty schema.
docker compose -f docker/docker-compose.standalone.yml stop backup
docker compose -f docker/docker-compose.standalone.yml up -d
scripts/restore.sh backups/study-assistant-<stamp>.tar.gz --yes

# 5. Verify the data is back through the API.
curl -s -X POST http://localhost/api/v1/auth/login \
  -H 'Content-Type: application/json' -c /tmp/drill-jar \
  -d '{"email":"drill@example.com","password":"correct-horse-battery"}'   # → 200
curl -s -b /tmp/drill-jar http://localhost/api/v1/courses                 # → "Restore Drill Course"
```

`scripts/restore.sh` prints exactly what it destroys (the `neuro_study`
database + the `data` volume) and refuses to run without `--yes` (or
`FORCE=1`). It uses `pg_restore --clean --if-exists`, so restoring over a
running instance works too.

## Demo notes

The demo flavor (`docker-compose.demo.yml`) runs the real app as a public
demo instance: isolated compose project + networks, database
**`neuro_study_demo`** (deployment.md: `neuro_<product>_demo`, never on a
production instance), synthetic-only data, badged **"Demo — synthetic
data"** in the SPA (the banner renders before login via the public
`GET /api/v1/instance/config`).

```bash
SA_DB_PASSWORD=… docker compose -f docker/docker-compose.demo.yml up -d --build
# → http://127.0.0.1:8090  (gateway binds loopback; front with a tunnel)
```

- **Demo guards (already wired, deployment.md):** `entrypoint.sh` aborts on
  demo configuration (`SA_DEMO_MODE=true`) unless `SA_APP_ENV=demo` is set
  explicitly — a production deployment can never run with demo data. The
  app sets `instance_settings.demo_mode=true` on first boot of the demo
  database (init-only, identity-auth §13).
- **Seeding is explicit and refused elsewhere:** the one-shot `demo-seed`
  service runs `scripts/seed-demo.py` (bind-mounted; the image ships only
  the backend — it does NOT auto-seed). The seeder refuses any target that
  is not a `*_demo` database (or an explicitly named `--demo-dir` for
  SQLite) on a `demo_mode=true` instance — and `--init-demo` only
  initializes an **empty** demo database. Seeding is idempotent;
  re-running changes no counts. Demo data is synthetic-only: clearly
  fictional users/courses/materials/notes/flashcards — the demo users
  share the documented password `DemoStudy!2026`.
- **Demo principal:** on demo instances the credential-free `demo` login
  (`POST /api/v1/auth/demo`) works next to the seeded personas;
  `demo` tokens are rejected while `demo_mode=false` (kit rules).
- **Public-demo posture:** `demo-net` is `internal: true` (zero egress —
  no AI providers, no web imports), only the gateway publishes a port
  (127.0.0.1 on the non-internal `edge` network), registration is disabled
  (`SA_REGISTRATION_ENABLED=false`), and the gateway starts only after
  `demo-seed` has completed successfully.
- **Reset (optional, `--profile reset`):** `demo-reset` purges previously
  seeded demo rows (and the demo principal's) and reseeds the pristine
  workspace on every `up` — visitor changes never accumulate:

  ```bash
  SA_DB_PASSWORD=… docker compose -f docker/docker-compose.demo.yml --profile reset up -d
  ```

  Full wipe: `docker compose -f docker/docker-compose.demo.yml --profile reset down -v`.
- **Restore drill:** the demo stack is disposable — no backup service. If
  you need one anyway, `scripts/backup.sh`/`restore.sh` work against any
  running stack (see the drill above; the database there is
  `neuro_study_demo`).

## Docker CLI cheat sheet

```bash
docker compose -f docker/docker-compose.standalone.yml exec app bash       # app shell
docker compose -f docker/docker-compose.standalone.yml logs -f app         # follow logs
docker compose -f docker/docker-compose.standalone.yml logs -f db
docker compose -f docker/docker-compose.standalone.yml exec app \
    sh -c 'SA_DATABASE_URL="$SA_MIGRATIONS_DATABASE_URL" /app/.venv/bin/alembic upgrade head'   # migrate manually (owner role)
docker compose -f docker/docker-compose.standalone.yml up -d --profile backup   # enable backups
docker compose -f docker/docker-compose.standalone.yml exec -T db \
    pg_isready -U neuro_study_owner -d neuro_study                         # DB health
```
