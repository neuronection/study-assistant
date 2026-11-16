#!/bin/bash
# Study Assistant — Postgres bootstrap (runs once via
# /docker-entrypoint-initdb.d, on first boot of an empty data volume).
#
# Creates the family roles from deployment.md / ADR-0064:
#   neuronection_study_owner — POSTGRES_USER: owns the schema and runs
#                              migrations (DDL); holds SA_DB_OWNER_PASSWORD.
#   neuronection_study_app  — runtime role: CONNECT + DML only, never DDL;
#                              holds SA_DB_PASSWORD (distinct from the
#                              owner's — a leaked app container must not
#                              gain DDL rights).
#
# docker-compose.prod.yml / standalone.yml pass SA_DB_APP_PASSWORD
# explicitly; dev flavors without it keep the legacy single-secret fallback
# (dev is not a deployment surface).
#
# Optionally creates the companion test database (POSTGRES_TEST_DB) next to
# the main DB — the dev-db flavor sets it to neuronection_study_test.
set -e

DB="${POSTGRES_DB:-neuronection_study}"
OWNER="${POSTGRES_USER:-neuronection_study_owner}"
APP_USER="${SA_DB_APP_USER:-neuronection_study_app}"
APP_PASSWORD="${SA_DB_APP_PASSWORD:-${SA_DB_PASSWORD:-${POSTGRES_PASSWORD:-}}}"
TEST_DB="${POSTGRES_TEST_DB:-}"

if [ -z "$APP_PASSWORD" ]; then
  echo "SA_DB_APP_PASSWORD (or SA_DB_PASSWORD / POSTGRES_PASSWORD for dev flavors) must be set — cannot create role '${APP_USER}'." >&2
  exit 1
fi

echo "Creating runtime role '${APP_USER}' (login, DML-only privileges)..."
psql -v ON_ERROR_STOP=1 -U "$OWNER" -d "$DB" \
    -v app_user="$APP_USER" -v app_password="$APP_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_user')
\gexec
SQL

grant_app_dml() {
  echo "Granting runtime (DML-only) privileges on '$1' to '${APP_USER}'..."
  psql -v ON_ERROR_STOP=1 -U "$OWNER" -d "$1" -v app_user="$APP_USER" <<'SQL'
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'app_user')
\gexec
GRANT USAGE ON SCHEMA public TO :"app_user";
-- Migrations run as the owner role, so its future objects pick up the
-- runtime grants automatically (no DDL for the app role, ever).
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO :"app_user";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app_user";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app_user";
SQL
}

grant_app_dml "$DB"

if [ -n "$TEST_DB" ]; then
  echo "Creating test database '$TEST_DB' if missing..."
  psql -v ON_ERROR_STOP=1 -U "$OWNER" -d "$DB" -v test_db="$TEST_DB" <<'SQL'
SELECT format('CREATE DATABASE %I', :'test_db')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'test_db')
\gexec
SQL
  grant_app_dml "$TEST_DB"
fi

echo "Database bootstrap complete."
