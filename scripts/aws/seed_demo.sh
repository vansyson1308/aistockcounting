#!/usr/bin/env bash
# Seed the demo tenant with a POS inventory snapshot for the three demo trays,
# so every scan has an expected count to compare against.
#
# Usage:
#   scripts/aws/seed_demo.sh https://dxxxxxxxxxxxx.cloudfront.net
#   scripts/aws/seed_demo.sh http://localhost          # local docker compose
#   scripts/aws/seed_demo.sh                           # CloudFrontUrl of $STACK_NAME
#
# Environment: TENANT_KEY (default demo), BRANCH_CODE (default MAIN, the scan
# page's default branch), API_TOKEN (sent as X-API-TOKEN when simple auth is
# on), STACK_NAME / AWS_REGION (used only when no URL is given).
# Safe to re-run: the backend uses the most recent snapshot per tray.
set -euo pipefail

BASE_URL="${1:-}"
if [[ -z "$BASE_URL" ]]; then
  BASE_URL="$(aws cloudformation describe-stacks --stack-name "${STACK_NAME:-TrayAgent}" \
    --region "${AWS_REGION:-ap-southeast-1}" \
    --query "Stacks[0].Outputs[?OutputKey=='CloudFrontUrl'].OutputValue" --output text)"
fi
BASE_URL="${BASE_URL%/}"
TENANT_KEY="${TENANT_KEY:-demo}"
BRANCH_CODE="${BRANCH_CODE:-MAIN}"

# tray_code expected_count product_name
TRAYS=(
  "TRAY-A 12 Demo rings (tray A)"
  "TRAY-B 12 Demo rings (tray B)"
  "TRAY-C 40 Demo earrings (tray C)"
)

items=""
for tray in "${TRAYS[@]}"; do
  read -r code count name <<<"$tray"
  items+="${items:+,}{\"branch_code\":\"$BRANCH_CODE\",\"tray_code\":\"$code\",\"sku\":\"DEMO-$code\","
  items+="\"product_name\":\"$name\",\"expected_count\":$count,\"source_ref\":\"seed_demo.sh\"}"
done
payload="{\"tenant_key\":\"$TENANT_KEY\",\"items\":[$items]}"

headers=(-H "Content-Type: application/json" -H "X-TENANT-KEY: $TENANT_KEY")
[[ -n "${API_TOKEN:-}" ]] && headers+=(-H "X-API-TOKEN: $API_TOKEN")

url="$BASE_URL/api/v1/integrations/kiotviet/inventory-snapshots"
echo "POST $url"
curl -fsS --max-time 30 -X POST "${headers[@]}" --data "$payload" "$url"
echo
echo "Seeded tenant '$TENANT_KEY', branch '$BRANCH_CODE': TRAY-A=12, TRAY-B=12, TRAY-C=40"
