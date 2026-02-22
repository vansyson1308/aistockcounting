#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost/api/v1}"
IMAGE_PATH="${1:-scripts/generated_sample.jpg}"
TRAY_ID="${TRAY_ID:-TRAY-DEMO}"
STAFF_ID="${STAFF_ID:-EMP-DEMO}"

if [[ ! -f "$IMAGE_PATH" ]]; then
  echo "Sample image not found: $IMAGE_PATH"
  echo "Run: ./scripts/gen_sample_image.py"
  exit 1
fi

echo "POST $API_BASE/count-items"
RESP=$(curl -sS -X POST "$API_BASE/count-items" \
  -F "image=@${IMAGE_PATH};type=image/jpeg" \
  -F "tray_id=${TRAY_ID}" \
  -F "staff_id=${STAFF_ID}")

echo "$RESP" | python -m json.tool
