#!/usr/bin/env bash
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/vj-inventory/current}
ENV_FILE=${ENV_FILE:-$APP_DIR/.env}
COMPOSE_FILE=${COMPOSE_FILE:-$APP_DIR/docker-compose.staging.yml}
SNAPSHOT_DIR=${SNAPSHOT_DIR:-/opt/vj-inventory/releases}

mkdir -p "$SNAPSHOT_DIR"

rollback() {
  latest=$(ls -1dt "$SNAPSHOT_DIR"/* 2>/dev/null | head -n1 || true)
  if [[ -z "$latest" ]]; then
    echo "No snapshot found for rollback" >&2
    exit 1
  fi
  cp "$latest/.env" "$ENV_FILE"
  cp "$latest/docker-compose.staging.yml" "$COMPOSE_FILE"
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d
  "$APP_DIR/ops/smoke_test.sh"
}

if [[ "${1:-}" == "rollback" ]]; then
  rollback
  exit 0
fi

ts=$(date +%Y%m%d_%H%M%S)
mkdir -p "$SNAPSHOT_DIR/$ts"
cp "$ENV_FILE" "$SNAPSHOT_DIR/$ts/.env"
cp "$COMPOSE_FILE" "$SNAPSHOT_DIR/$ts/docker-compose.staging.yml"

cd "$APP_DIR"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" pull || true
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d
"$APP_DIR/ops/smoke_test.sh"

echo "Deploy completed. Snapshot: $SNAPSHOT_DIR/$ts"
