# Study Assistant - Docker Utilities & Cheat Sheet

This directory contains the Docker configuration files for Study Assistant.
It mirrors Health and Career Assistant's docker layout (family standard).

For desktop/development on the host see `docs/` and `scripts/run-dev.sh`.

## File map

| File | Purpose |
|---|---|
| `docker-compose.standalone.yml` | Canonical self-hosted single-host web stack: backend (API + SPA) + nginx (TLS-ready). SQLite by design — no Postgres service; all state lives in the `data` volume. |
| `Dockerfile` | Multi-stage: pnpm frontend bundle → uv-managed backend image serving API + SPA from one uvicorn process. |
| `entrypoint.sh` | Runs migrations, starts uvicorn in web mode. |
| `nginx.conf` | HTTP-only reverse proxy incl. the `/ws` WebSocket endpoint (loopback / VPN). |
| `nginx-TLS.conf` | TLS-terminating variant (certbot webroot ACME + HSTS). |

## Self-hosting (standalone flavor)

```bash
docker compose -f docker/docker-compose.standalone.yml up -d --build
# → http://localhost
```

- All persistent state (database `app.db`, blobs, cache, backups) lives under
  `SA_DATA_DIR=/data` (named volume `data`). Back it up by backing up the
  volume: `docker run --rm -v study-assistant_data:/data -v "$PWD":/backup
  alpine tar czf /backup/study-data.tgz -C /data .`
- Deploy a pre-built image instead of building:
  `STUDY_IMAGE=ghcr.io/<owner>/<repo>:<tag> docker compose ... up -d`
- Scaling note: SQLite + one data volume → run exactly **one** backend
  replica. Horizontal scale requires a server DB (out of scope by ADR).

## TLS

The default `nginx.conf` is HTTP-only — use it only behind a VPN or on
loopback. For internet-facing deployments:

1. Mount `nginx-TLS.conf` over `nginx.conf` (uncomment the commented volumes
   in the compose file, including `443:443`).
2. Provide certs at `docker/certs/fullchain.pem` + `privkey.pem`
   (certbot webroot renewals answer on port 80 via
   `/.well-known/acme-challenge/`).
3. Set `SERVER_NAME` in the conf to your domain.

## Docker CLI cheat sheet

```bash
docker compose -f docker/docker-compose.standalone.yml exec backend bash  # app shell
docker compose -f docker/docker-compose.standalone.yml logs -f backend    # follow logs
docker compose -f docker/docker-compose.standalone.yml run --rm backend \
    /app/.venv/bin/alembic upgrade head                                   # migrate manually
```
