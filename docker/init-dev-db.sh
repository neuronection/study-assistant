#!/bin/bash
# Creates the per-variant test database alongside neuronection_study on first boot
# (career's init-test-db.sh pattern).
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    SELECT 'CREATE DATABASE $POSTGRES_TEST_DB'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$POSTGRES_TEST_DB')\gexec
EOSQL
