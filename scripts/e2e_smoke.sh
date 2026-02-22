#!/usr/bin/env bash
set -euo pipefail

FRONTEND_URL="${FRONTEND_URL:-http://localhost}"
BACKEND_HEALTH_URL="${BACKEND_HEALTH_URL:-http://localhost:8000/health}"


echo "1) Health checks"
curl -fsS "$FRONTEND_URL" >/dev/null && echo "Frontend reachable"
curl -fsS "$BACKEND_HEALTH_URL" | python -m json.tool

echo "2) Upload sample to backend via nginx API"
./scripts/gen_sample_image.py >/dev/null
API_BASE="${API_BASE:-http://localhost/api/v1}" ./scripts/upload_sample.sh scripts/generated_sample.jpg

echo "3) Manual follow-up"
echo "- Save result from frontend /scan"
echo "- Verify /history shows new record"
echo "- Verify /history/{id} loads detail"
echo "- Verify /stats reflects total_records increment"
