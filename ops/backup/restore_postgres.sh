#!/usr/bin/env bash
set -euo pipefail

DUMP_PATH=${1:?Usage: restore_postgres.sh <postgres.dump> [target_db]}
TARGET_DB=${2:-stockdb_restore}

: "${POSTGRES_USER:=postgres}"
: "${POSTGRES_PASSWORD:=postgres}"

export PGPASSWORD="$POSTGRES_PASSWORD"
psql -h localhost -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS $TARGET_DB;"
psql -h localhost -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE $TARGET_DB;"
pg_restore -h localhost -U "$POSTGRES_USER" -d "$TARGET_DB" "$DUMP_PATH"
echo "Restored to database: $TARGET_DB"
