# syntax=docker/dockerfile:1
# Study Assistant — multi-stage build: pnpm frontend bundle → uv-managed
# backend image serving API + SPA from one uvicorn process (web mode).
#
# SQLite is the datastore by design (local-first, ADR-backed); all persistent
# state lives under SA_DATA_DIR (mount a volume there).

FROM node:24-alpine AS frontend-build
WORKDIR /build
RUN npm install -g pnpm@11
COPY pnpm-workspace.yaml pnpm-lock.yaml ./
COPY package.json ./
COPY frontend/package.json frontend/
RUN pnpm install --frozen-lockfile
COPY frontend/ frontend/
RUN pnpm --filter frontend build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    SA_PORT=8000 \
    SA_HOST=0.0.0.0 \
    SA_DATA_DIR=/data \
    SA_SPA_DIST=/app/frontend/dist

WORKDIR /app
RUN useradd --create-home --shell /usr/sbin/nologin study \
    && mkdir -p /data && chown study:study /data

# Dependency layer: workspace manifests + lockfile first so code changes
# don't bust the uv cache.
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/app backend/app
COPY backend/studyassistant backend/studyassistant
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
# Web mode never imports pywebview/PyGObject (desktop shell) — skip them and
# their GTK system dependencies (pycairo would need a source build).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
      --no-install-package pywebview \
      --no-install-package pygobject \
      --no-install-package pycairo

# Code layer
COPY backend/alembic backend/alembic
COPY backend/alembic.ini backend/alembic.ini
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

COPY --from=frontend-build --chown=study:study /build/frontend/dist frontend/dist

USER study
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3); sys.exit(0 if r.status < 500 else 1)"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
