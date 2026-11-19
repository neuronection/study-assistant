# Deployment

Study Assistant ships two ways: as a **desktop app** (pywebview over the built
SPA, covered in [desktop-packaging.md](desktop-packaging.md)) and as a
**self-hosted web service** served from one Docker stack (T1 on-prem / cloud
VM; the deployment contract). This page covers the web deployment: the
release-bundle installer, the standalone compose stack, nginx and TLS, the
data volume, environment variables, upgrades and backups. The Docker file map
is also summarized in `docker/README.md`.

## Server install from a release bundle

The supported server path — no source checkout, no build toolchain on the
host. Every GitHub release attaches a **source-free bundle**:
`study-compose-vX.Y.Z.tar.gz` + `manifest.json` (image pinned by digest) +
`SHA256SUMS`. The bundle carries `docker/` (compose files, nginx configs, env
example, entrypoint, `init-db.sh`, backup sidecar) +
`scripts/{install,update,backup,restore,lib-docker}.sh` + `installer.json`
(the product config). No source tree, no `.env`, no secrets.

Prerequisites: a Linux host (Ubuntu 22.04/24.04 reference) with **Docker +
Docker Compose v2**, ≥ 4 GB RAM, ~5 GB free disk, a non-root user in the
`docker` group. The installer never runs as root, never installs packages,
never overwrites an existing env file.

One-liner (the bootstrap resolves the latest release, verifies the bundle
SHA-256, extracts and hands off to the audited in-bundle installer):

```bash
curl -fsSL https://neuronection.com/install/study.sh | bash
# cautious form: download it, read it, then run it
curl -fsSL https://neuronection.com/install/study.sh -o study-bootstrap.sh
less study-bootstrap.sh
bash study-bootstrap.sh --dir ~/study-assistant
```

Bootstrap flags: `--dir DIR`, `--ref vX.Y.Z` (pin an exact release),
`--dry-run` (resolve + verify + print the hand-off, write nothing), `--offline
study-compose-vX.Y.Z.tar.gz` (already-downloaded bundle, no network
download), and `--` to forward installer flags — e.g.
`-- --http-port 8091`. The one-liner URL 302-redirects to the GitHub
release asset (trust anchor = the release, not the website); until that
route is published, use the asset from the release page.

Manual, without the bootstrap:

```bash
# from the release: study-compose-vX.Y.Z.tar.gz + manifest.json + SHA256SUMS
sha256sum -c SHA256SUMS
mkdir -p ~/study-assistant
tar -xzf study-compose-vX.Y.Z.tar.gz -C ~/study-assistant
cp manifest.json ~/study-assistant/          # installer pins the image digest from it
cd ~/study-assistant
bash scripts/install.sh
```

What `scripts/install.sh` does (see [docker/README.md](../../docker/README.md)
for the full flag table): generates the env file from the example with the
five per-instance secrets (`SA_DB_OWNER_PASSWORD`, `SA_DB_PASSWORD`,
`SA_SESSION_KEY`, `SA_REFRESH_KEY`, `SA_DATA_KEY` — `umask 077`, never
printed, never overwritten on a re-run) → pins `STUDY_IMAGE` from the release
manifest (the bootstrap forwards `--image app=<digest>`; priority: `--image
[KEY=]REF` > `--image-tag` > `$STUDY_IMAGE` > manifest > existing env) →
sets `HTTP_PORT` → pre-flights published ports → pulls → `up -d --no-build`
→ waits for `/api/v1/health` → prints the URL and the first-admin note. Exit
codes: `0` ok · `1` usage/prereq · `2` image pull · `3` compose config/start
or health · `4` port conflict.

Port plan: the bundle publishes one host port (`HTTP_PORT`, default 80).
Multiple Neuronection stacks on one host get distinct ports
(`--http-port 8090/8091/8092` for health/study/career).

### Updating a bundle install

1. Read the release notes; take a backup (`scripts/backup.sh` — off-host
   targets via `SA_BACKUP_RCLONE_REMOTE` / `SA_BACKUP_S3_URI` /
   `SA_BACKUP_AZURE_URL`, encryption via `SA_BACKUP_AGE_RECIPIENT`).
2. Download the new release's bundle + `manifest.json` + `SHA256SUMS`.
3. Extract over the install directory — the env file is not in the bundle,
   so secrets and settings survive; copy the new `manifest.json` in.
4. `bash scripts/update.sh` — bumps `STUDY_IMAGE` to the new manifest
   digest, pulls, `up -d --no-build`, waits for `/api/v1/health`. No git,
   no rebuild: the previous image pin is kept (a comment in the env file +
   the printed rollback command) and no destructive data operation ever
   runs.

Rollback: `bash scripts/update.sh --image <previous pin>` (recorded in the
env file), and restore the pre-upgrade dump with `scripts/restore.sh` if
the release migrated the schema — pre-1.0 there is no downgrade path, so
keep the previous bundle and a backup before every update.

## The standalone stack

`docker/docker-compose.standalone.yml` is the canonical self-hosted stack:

- **backend** — one uvicorn process serving the `/api/v1` API, the `/ws`
  WebSocket and the built SPA, built by the multi-stage `docker/Dockerfile`
  (pnpm frontend bundle → uv-managed backend image). `entrypoint.sh serve`
  boots it with the **app DSN only** — it never runs migrations or DDL.
- **migrate** — the one-shot mode: role bootstrap (app role + grants +
  default privileges + `vector`/`pg_trgm`), Alembic, checkpoint schema — all
  as the owner role, then exit (the migration sequence, the credential policy).
- **nginx** — a reverse proxy in front of the backend, including the `/ws`
  upgrade and the `/ready` probe. `nginx.conf` is HTTP-only;
  `nginx-TLS.conf` is the TLS-terminating variant.

```bash
docker compose -f docker/docker-compose.standalone.yml up -d --build
# → http://localhost
```

Deploy a pre-built image instead of building by setting
`STUDY_IMAGE=ghcr.io/<owner>/<repo>:<tag>`.

### Cloud object storage (S3/Azure)

A cloud deployment adds the object-storage overlay to the prod (or
standalone) compose file:

```bash
docker compose -f docker/docker-compose.prod.yml \
               -f docker/docker-compose.cloud.yml up -d
```

Set `SA_CLOUD_PROFILE` (`aws` / `azure`) and
`SA_OBJECT_STORAGE_BACKEND` (`s3` / `azure_blob`) plus the provider values in
`docker/.env`. Azure deployments should prefer managed identity; an
S3-compatible gateway (for example MinIO on Azure) uses
`SA_OBJECT_STORAGE_BACKEND=s3` under the azure profile. Leave
`SA_OBJECT_STORAGE_MAX_MB` unset so study's 200 MB host
upload cap applies; the compose files intentionally pass it as empty rather
than the contract's 100 MB default. The backup sidecar still dumps
PostgreSQL, but skips its `/data` tar under object storage (provider
durability owns the blobs). See
[storage.md](storage.md#cloud-deployment-checklist) for the cloud
deployment checklist and provider examples.

### Ops scripts

| Script | Purpose |
|---|---|
| `scripts/install.sh` | Release-bundle installer (see *Server install from a release bundle*): env + secrets + pin + port pre-flight + `up -d` + health-wait |
| `scripts/update.sh` | Release-bundle updater: bump the `STUDY_IMAGE` pin (previous pin kept), pull, `up -d --no-build`, health-wait |
| `scripts/run-docker.sh` | Source checkouts, first-time deploy: build, `up -d`, wait for healthy |
| `scripts/update-docker.sh` | Source checkouts, refresh an existing install: best-effort `git pull` → rebuild (or pull `STUDY_IMAGE`) → `up -d` → health-wait. `--no-pull` / `--no-wait` |
| `scripts/lib-docker.sh` | Shared helpers sourced by the scripts above |

All of them are idempotent and never touch the `data` volume except the
explicit `install.sh --reset`.

## Databases

Web/server mode runs **PostgreSQL 16** (`pgvector/pgvector` image, database
`neuronection_study`, owner + app roles — see `docker/README.md`): the `db` service
holds all structured state and the app connects through `SA_DATABASE_URL`
(or `SA_DB_NAME`/`SA_DB_USER`/`SA_DB_PASSWORD`/`SA_DB_HOST`/`SA_DB_PORT`).
Desktop mode keeps SQLite (`<data_dir>/study.sqlite3` +
`checkpoints.sqlite3`). Blobs, cache and backups stay under
`SA_DATA_DIR=/data` (named `data` volume). Migrations run in the one-shot
`migrate` service (owner role) and are verified on both dialects in CI.

### Two roles, two credentials (the credential policy)

| Role | Credential | Used by | Privileges |
|---|---|---|---|
| `neuronection_study_owner` | `SA_DB_OWNER_PASSWORD` (`SA_MIGRATIONS_DATABASE_URL`) | the one-shot `migrate` service, the backup sidecar (`pg_dump`) | DDL: schema, extensions, checkpoint tables, grants |
| `neuronection_study_app` | `SA_DB_PASSWORD` (`SA_DATABASE_URL`) | `app` (web), workers | DML only: SELECT/INSERT/UPDATE/DELETE |

The owner DSN **never appears in the `app` service's environment** — the
entrypoint refuses to serve when it does (a serving process that carries it
would silently regain DDL rights). Migrate mode resolves the the credential policy
tri-state:

- **split** — app URL + `SA_MIGRATIONS_DATABASE_URL` + `SA_DB_SPLIT=1`
  (the shipped compose shape): supported;
- **unsplit** — neither the migrations URL nor the marker: boots with a loud
  warning; **not managed-ready**;
- **broken** — `SA_DB_SPLIT=1` without a migrations URL: refuses to boot.

Every `migrate` run (as owner) bootstraps/syncs the app role: `CREATE ROLE`
if missing, `ALTER ROLE ... PASSWORD` when `SA_DB_PASSWORD` rotated, the
DML-only grants, `ALTER DEFAULT PRIVILEGES` (so future owner objects are
usable at runtime), and verification-or-creation of the `vector` /
`pg_trgm` extensions. Rotation recipe: change `SA_DB_PASSWORD`, then
`docker compose ... up -d` — migrate applies it before the app starts.

**0.13 is a one-way datastore break.** A PostgreSQL volume from 0.12.x cannot be
upgraded: the `migrate` service preflights `alembic_version` and exits with
guidance (`docker compose down -v` destroys the volume; or stay on 0.12.1). It
never drops data automatically. Desktop SQLite quarantines the old datastore and
shows a one-time notice (the family datastore-break policy).

Legacy installs adopt the current database names automatically: both deploy
scripts run `migrate_legacy_db_names()` (`scripts/lib-docker.sh`) before the
stack boots — a guarded, idempotent `ALTER DATABASE` / `ALTER ROLE` rename of
`neuro_*` databases and roles that no-ops on fresh or already-renamed
stacks. Manual recipes (dev DBs, demo) live in `docker/README.md` →
"Renaming `neuro_*` → `neuronection_*`".

## Managed readiness (the deployment contract §5 / the credential policy)

Study is the family's **managed-DB reference** (`databaseMode=managed`,
clinic profile). What a managed provider must give the provisioning seam:

- a provider admin (`azure_pg_admin` on Azure Flexible, `rds_superuser` on
  RDS) that **allow-lists and pre-creates the `vector` and `pg_trgm`
  extensions** — the product owner cannot `CREATE EXTENSION` there, and
  migrate verifies presence first (a missing, uncreatable extension fails
  loud with the allow-list note instead of a raw privilege error);
- a product owner role the migrations URL authenticates as, owning the
  schema; migrate creates the app role from it, grants DML-only, and sets
  `ALTER DEFAULT PRIVILEGES` so objects created by later migrations stay
  usable without a manual re-grant;
- the langgraph checkpoint schema is DDL too — it is provisioned **owner-side
  in `migrate`** (`app.ops.migrations`), never at web boot;
- the dimension-independent v1 vector tables (`vec_meta`, `chunk_vec_ids`)
  are pre-created owner-side as well, so the write path's `IF NOT EXISTS`
  statements become no-ops.

#### Vector store provisioning (v1 `chunk_vecs`)

`chunk_vecs` is dimension-qualified (`vector(<dim>)`, dim = your configured
embeddings model's output size), so migrate cannot guess it on a fresh
install. Under the split the app role cannot create it — the first
semantic-search ingest fails **typed** (`VectorProvisioningError`) with the
recipe instead of a raw privilege error:

```bash
docker compose exec db psql -U neuronection_study_owner -d neuronection_study -c "
CREATE TABLE IF NOT EXISTS chunk_vecs
  (rowid BIGINT PRIMARY KEY, chunk_embedding vector(1536));
CREATE INDEX IF NOT EXISTS ix_chunk_vecs_embedding
  ON chunk_vecs USING hnsw (chunk_embedding vector_cosine_ops);"
```

(Use your model's dimension — 1536 for `text-embedding-3-small`; the full
provisioning seam that resolves it from the configured model is the deployment contract
§3.3's remaining work.) Legacy installs that already wrote vectors are
unaffected; a later model/dim change follows the designed new-space handoff
(`VectorSpaceChangeRequired`, the vector provisioning rule).

`compose-selfhosted` remains **supported**, verified with v0.13.0 (see
`docs/deployment-tiers.json`); `managed-db` is best-effort until a manual
provider deployment closes it.

## Probes

- `GET /api/v1/health` — **liveness** (compose healthcheck): 200 unless the
  DB or required storage is down.
- `GET /ready` — **readiness** (ingress/load-balancer probe): 200 only when
  the DB is reachable **and stamped at this release's migration head**,
  required object storage answers, and boot (lifespan startup) completed.
  Soft signals — Redis (study has none: in-process schedulers), optional
  storage degradation — are reported but never flip the status. Not ready →
  **503** with a per-check breakdown. Negative tests:
  `backend/tests/test_ready_endpoint.py`.

## Environment

The compose files set `SA_DEBUG=0`, `SA_PORT=8000`, `SA_HOST=0.0.0.0`,
`SA_DATA_DIR=/data`, `SA_SPA_DIST=/app/frontend/dist`, the `SA_DATABASE_URL`
of the `db` service and the five guarded secrets (`SA_DB_OWNER_PASSWORD`,
`SA_DB_PASSWORD`, `SA_SESSION_KEY`, `SA_REFRESH_KEY`, `SA_DATA_KEY`) via a
`docker/.env` with `:?` guards. Configuration is via
`SA_*` env vars (see `backend/app/core/config.py`); **there are no AI secrets in
the environment** — API keys are entered in the app and stored in the OS keyring
of the host running the backend. A root `.env` is honored but not required
(`scripts/install.sh` prefers `docker/.env` and falls back to a root `.env`
from a source-checkout install).

## TLS

The default `nginx.conf` is HTTP-only — use it only on loopback or behind a
VPN. For internet-facing deployments:

1. Mount `nginx-TLS.conf` over `nginx.conf` (uncomment the commented volumes in
   the compose file, including `443:443`).
2. Provide certs at `docker/certs/fullchain.pem` + `privkey.pem` (certbot
   webroot renewals answer on port 80 via `/.well-known/acme-challenge/`).
3. Set `SERVER_NAME` in the conf to your domain.

The TLS variant sends HSTS. For why this matters beyond transport security — install, share target, microphone and Media Session all need a secure context — see [tls-and-secure-context.md](tls-and-secure-context.md).

### Cookie `Secure` is derived, never static (the deployment contract §9)

`SA_COOKIE_SECURE` is **derived from the public scheme** — declare where
public traffic terminates and the app derives the flag:

```bash
# public https:// (nginx-TLS or BYO proxy):
SA_PUBLIC_URL=https://study.example.com
# LAN/VPN plain HTTP — login keeps working (Secure would break it):
SA_PUBLIC_URL=http://192.0.2.10
# TLS terminates on another host's proxy (cloud LB):
SA_TLS=1
```

An explicit `SA_COOKIE_SECURE=true|false` still wins (rare; for unusual
setups). The compose files pass these through empty and never hard-code a
value, so LAN/VPN logins over HTTP cannot be locked out by a forgotten
flag. `SA_TRUSTED_PROXY_COUNT` (default 1 behind the shipped nginx, 0 on
the prod flavor's direct bind) says how many rightmost `X-Forwarded-For`
hops to believe for rate limiting and client IP. Proxy limits: nginx
read/send 300 s for AI/SSE, 3600 s for `/ws`; if you front study with
Cloudflare, its ~100 s proxy timeout applies to SSE streams.

## Backups

**Backup is a service, not a ritual** (deployment.md; the backup policy): the
`backup` sidecar (`--profile backup`) writes scheduled `pg_dump -Fc` files
into `docker/backups/`, and `scripts/backup.sh` / `scripts/restore.sh`
take/restore full snapshots (database dump + `data` volume). The app's own
`BackupScheduler` additionally writes validated archives into
`<SA_DATA_DIR>/backups/` (see [jobs.md](jobs.md)):

```bash
docker run --rm -v study-assistant_data:/data -v "$PWD":/backup \
  alpine tar czf /backup/study-data.tgz -C /data .
```

In-app restore (upload or stored-by-name) is available from Settings → Data.

### Off-host upload + run ledger (the backup policy)

A T1 backup must leave the host. `scripts/backup.sh` uploads the finished
archive to every configured target (rclone / aws s3 / azcopy) and — when the
destination is shared — encrypts it first:

```bash
SA_BACKUP_RCLONE_REMOTE=myremote:study-backups   # rclone copy
SA_BACKUP_S3_URI=s3://my-bucket/study            # aws s3 cp
SA_BACKUP_AZURE_URL=https://acct.blob.core.windows.net/cont/study?<sas>  # azcopy copy
SA_BACKUP_AGE_RECIPIENT=age1...                  # age-encrypt before upload
```

`SA_BACKUP_AGE_RECIPIENT` (family alias `BACKUP_AGE_RECIPIENT`) seals the
archive with your age public key — only the `.age` file leaves the host, and
`scripts/restore.sh` decrypts it with the operator's age identity; keep the
private key offline, never on the server.

Every run appends one JSONL row to `backups/backup_runs.jsonl`
(`run_at`, `archive`, `bytes`, `sha256`, `uploaded_to`, `status`):
`uploaded`, `local-only` (no target configured — on T1 that is a DR gap,
not a success) or `upload-failed` (the script exits non-zero). Alert on
staleness: a row older than 2× the backup interval means the service
stopped, and `backup_runs.jsonl` is the thing that tells you.

### Restore drill

Rehearse the drill before you need it (the backup policy):

1. **Throwaway target first.** Restore into a scratch database + volume,
   never over the live stack while it serves: bring a temp project up (or
   `pg_restore` into `study_drill` on the same server).
2. `scripts/restore.sh <archive> --yes` restores the DB (as owner), then
   **re-grants the app role** its DML-only set (the dump carries ownership,
   not runtime grants) and unpacks the data volume.
3. **Verify named counts + a known record**: e.g. `SELECT count(*) FROM
   courses`, plus one known row (a course title or a blob sha) compared
   against the source. A restore that satisfies neither is failed.
4. Record the drill in `backup_runs.jsonl`-adjacent notes (or your
   runbook) with date, archive, and the verified record.

## Bare metal / webapp mode

Without Docker you can serve the built SPA from the backend directly:

```bash
pnpm webapp          # build SPA + serve + open browser
```

Set `SA_HOST`/`SA_PORT` and run `python -m studyassistant web` for a headless
server. The desktop app remains the default local mode.

## Docker CLI cheat sheet

```bash
docker compose -f docker/docker-compose.standalone.yml exec app bash
docker compose -f docker/docker-compose.standalone.yml logs -f app
docker compose -f docker/docker-compose.standalone.yml exec db \
    psql -U neuronection_study_owner -d neuronection_study
```

Changes to `docker/`, the ops scripts or the dev entrypoints must update this
page, `docker/README.md`, the README quick-start and `docs/STATUS.md` in the
same commit.
