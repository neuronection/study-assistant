# Deployment

Study Assistant ships two ways: as a **desktop app** (pywebview over the built
SPA, covered in [desktop-packaging.md](desktop-packaging.md)) and as a
**self-hosted web service** served from one Docker stack. This page covers the
web deployment: the standalone compose stack, nginx and TLS, the data volume,
environment variables, upgrades and backups. The Docker file map is also
summarized in `docker/README.md`.

## The standalone stack

`docker/docker-compose.standalone.yml` is the canonical self-hosted stack:

- **backend** — one uvicorn process serving the `/api/v1` API, the `/ws`
  WebSocket and the built SPA, built by the multi-stage `docker/Dockerfile`
  (pnpm frontend bundle → uv-managed backend image). `entrypoint.sh` runs
  migrations then starts uvicorn in web mode.
- **nginx** — a reverse proxy in front of the backend, including the `/ws`
  upgrade. `nginx.conf` is HTTP-only; `nginx-TLS.conf` is the TLS-terminating
  variant.

```bash
docker compose -f docker/docker-compose.standalone.yml up -d --build
# → http://localhost
```

Deploy a pre-built image instead of building by setting
`STUDY_IMAGE=ghcr.io/<owner>/<repo>:<tag>`.

### Ops scripts

| Script | Purpose |
|---|---|
| `scripts/run-docker.sh` | First-time deploy: build, `up -d`, wait for healthy |
| `scripts/update-docker.sh` | Refresh an existing install: best-effort `git pull` → rebuild (or pull `STUDY_IMAGE`) → `up -d` → health-wait. `--no-pull` / `--no-wait` |
| `scripts/lib-docker.sh` | Shared helpers sourced by the two scripts above |

Both scripts are idempotent and never touch the `data` volume.

## Databases (ADR-0022)

Web/server mode runs **PostgreSQL 16** (`pgvector/pgvector` image, database
`neuro_study`, owner + app roles — see `docker/README.md`): the `db` service
holds all structured state and the app connects through `SA_DATABASE_URL`
(or `SA_DB_NAME`/`SA_DB_USER`/`SA_DB_PASSWORD`/`SA_DB_HOST`/`SA_DB_PORT`).
Desktop mode keeps SQLite (`<data_dir>/study.sqlite3` +
`checkpoints.sqlite3`). Blobs, cache and backups stay under
`SA_DATA_DIR=/data` (named `data` volume). Migrations run automatically on
start (owner role) and are verified on both dialects in CI.

## Environment

The compose file sets `SA_DEBUG=0`, `SA_PORT=8000`, `SA_HOST=0.0.0.0`,
`SA_DATA_DIR=/data`, `SA_SPA_DIST=/app/frontend/dist` and the
`SA_DATABASE_URL` of the `db` service (passwords come from `SA_DB_PASSWORD`
via a `docker/.env` with `:?` guards). Configuration is via
`SA_*` env vars (see `backend/app/core/config.py`); **there are no AI secrets in
the environment** — API keys are entered in the app and stored in the OS keyring
of the host running the backend. A root `.env` is honored but not required.

## TLS

The default `nginx.conf` is HTTP-only — use it only on loopback or behind a
VPN. For internet-facing deployments:

1. Mount `nginx-TLS.conf` over `nginx.conf` (uncomment the commented volumes in
   the compose file, including `443:443`).
2. Provide certs at `docker/certs/fullchain.pem` + `privkey.pem` (certbot
   webroot renewals answer on port 80 via `/.well-known/acme-challenge/`).
3. Set `SERVER_NAME` in the conf to your domain.

The TLS variant sends HSTS.

## Backups

**Backup is a service, not a ritual** (deployment.md): the `backup` sidecar
(`--profile backup`) writes scheduled `pg_dump -Fc` files into `docker/backups/`,
and `scripts/backup.sh` / `scripts/restore.sh` take/restore full snapshots
(database dump + `data` volume) — `docker/README.md` documents the restore
drill. The app's own `BackupScheduler` additionally writes validated archives
into `<SA_DATA_DIR>/backups/` (see [jobs.md](jobs.md)):

```bash
docker run --rm -v study-assistant_data:/data -v "$PWD":/backup \
  alpine tar czf /backup/study-data.tgz -C /data .
```

In-app restore (upload or stored-by-name) is available from Settings → Data.

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
    psql -U neuro_study_owner -d neuro_study
```

Changes to `docker/`, the ops scripts or the dev entrypoints must update this
page, `docker/README.md`, the README quick-start and `docs/STATUS.md` in the
same commit.
