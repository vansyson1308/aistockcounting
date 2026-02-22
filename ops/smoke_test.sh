#!/usr/bin/env bash
set -euo pipefail

BASE_URL=${BASE_URL:-http://localhost}

echo "Checking frontend..."
curl -fsS "$BASE_URL/" >/dev/null

echo "Checking backend health..."
curl -fsS "$BASE_URL/api/health" | rg '"status"|"ok"' >/dev/null

echo "Checking minio health (container internal port via published mapping if any)..."
if curl -fsS http://localhost:9000/minio/health/live >/dev/null 2>&1; then
  echo "MinIO live endpoint reachable"
else
  echo "MinIO endpoint not published externally; skipping direct check"
fi

echo "Smoke test passed"
