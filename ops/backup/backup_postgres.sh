#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR=${1:-/opt/vj-inventory/backups/$(date +%Y%m%d_%H%M%S)}
mkdir -p "$BACKUP_DIR"

: "${POSTGRES_USER:=postgres}"
: "${POSTGRES_DB:=stockdb}"
: "${POSTGRES_PASSWORD:=postgres}"

export PGPASSWORD="$POSTGRES_PASSWORD"
pg_dump -h localhost -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$BACKUP_DIR/postgres.dump"
echo "$BACKUP_DIR/postgres.dump"
