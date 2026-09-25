#!/usr/bin/env bash
# Deploy TrayAgent to AWS: CDK stack, arm64 images in ECR, model in S3, then
# restart the containers on the EC2 host and wait for the public health check.
#
# Usage:
#   scripts/aws/deploy.sh
#   AWS_REGION=ap-southeast-1 INSTANCE_TYPE=c7g.large ALARM_EMAIL=me@example.com scripts/aws/deploy.sh
#   MODEL_PATH=models/trayagent_v1.onnx scripts/aws/deploy.sh
#
# Environment (all optional):
#   AWS_REGION        target region                           (default ap-southeast-1)
#   STACK_NAME        CloudFormation stack name               (default TrayAgent)
#   INSTANCE_TYPE     t4g.* or c7g.*                          (default t4g.large)
#   IMAGE_TAG         image tag to build and run              (default: git short SHA)
#   ENABLE_BEDROCK    true to use the Bedrock planner         (default false)
#   BEDROCK_MODEL_ID  model / inference profile id; required with ENABLE_BEDROCK=true
#   ALARM_EMAIL       email subscribed to the alarm topic (confirm the SNS email)
#   MODEL_PATH        local ONNX model to upload; its sidecar <name>.json is uploaded too
#   MODEL_S3_KEY      S3 key of the model (default models/trayagent_v1.onnx when
#                     MODEL_PATH is set). Set it without MODEL_PATH to keep using a
#                     model uploaded earlier; with neither, the classical detector runs.
#   HEALTH_TIMEOUT    seconds to wait for https://<cloudfront>/api/health (default 600)
#
# Idempotent: re-running it redeploys the same state. Needs: aws CLI v2 with
# credentials, docker with buildx (plus QEMU binfmt for arm64 on x86 hosts),
# node/npx and python3. No SSH: the host is managed through SSM.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INFRA_DIR="$REPO_ROOT/infra/aws"

export AWS_REGION="${AWS_REGION:-ap-southeast-1}"
export AWS_DEFAULT_REGION="$AWS_REGION"
STACK_NAME="${STACK_NAME:-TrayAgent}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t4g.large}"
IMAGE_TAG="${IMAGE_TAG:-$(git -C "$REPO_ROOT" rev-parse --short HEAD)}"
ENABLE_BEDROCK="${ENABLE_BEDROCK:-false}"
BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-}"
ALARM_EMAIL="${ALARM_EMAIL:-}"
MODEL_PATH="${MODEL_PATH:-}"
MODEL_S3_KEY="${MODEL_S3_KEY:-}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-600}"

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not installed"; }

# ---- 0. Preflight -------------------------------------------------------------
for tool in aws docker node npx python3 git curl; do need "$tool"; done
docker buildx version >/dev/null 2>&1 || die "docker buildx is required"
[[ "$IMAGE_TAG" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]] || die "invalid IMAGE_TAG: $IMAGE_TAG"
if [[ -n "$MODEL_PATH" ]]; then
  [[ -f "$MODEL_PATH" ]] || die "MODEL_PATH not found: $MODEL_PATH"
  MODEL_S3_KEY="${MODEL_S3_KEY:-models/trayagent_v1.onnx}"
fi
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)" ||
  die "no AWS credentials (aws sts get-caller-identity failed)"
if ! docker buildx inspect --bootstrap 2>/dev/null | grep -q 'linux/arm64'; then
  die "this buildx builder cannot build linux/arm64. On x86 install QEMU first:
  docker run --privileged --rm tonistiigi/binfmt --install arm64"
fi
echo "account $ACCOUNT_ID, region $AWS_REGION, stack $STACK_NAME, $INSTANCE_TYPE, tag $IMAGE_TAG"

# CDK toolchain: Python venv for the app, the pinned CLI from package.json.
if [[ ! -x "$INFRA_DIR/.venv/bin/python" ]]; then
  log "Creating infra/aws/.venv"
  python3 -m venv "$INFRA_DIR/.venv"
fi
"$INFRA_DIR/.venv/bin/pip" install --quiet --disable-pip-version-check -r "$INFRA_DIR/requirements.txt"
[[ -x "$INFRA_DIR/node_modules/.bin/cdk" ]] || (cd "$INFRA_DIR" && npm ci --no-audit --no-fund)
cdk() { (cd "$INFRA_DIR" && ./node_modules/.bin/cdk "$@"); }

context=(
  -c "stackName=$STACK_NAME"
  -c "region=$AWS_REGION"
  -c "instanceType=$INSTANCE_TYPE"
  -c "enableBedrock=$ENABLE_BEDROCK"
)
[[ -n "$BEDROCK_MODEL_ID" ]] && context+=(-c "bedrockModelId=$BEDROCK_MODEL_ID")
[[ -n "$ALARM_EMAIL" ]] && context+=(-c "alarmEmail=$ALARM_EMAIL")
[[ -n "$MODEL_S3_KEY" ]] && context+=(-c "modelS3Key=$MODEL_S3_KEY")

# ---- 1-2. Infrastructure --------------------------------------------------------
log "cdk bootstrap (no-op when the environment is already bootstrapped)"
cdk bootstrap "aws://$ACCOUNT_ID/$AWS_REGION" "${context[@]}"

log "cdk deploy $STACK_NAME"
cdk deploy "$STACK_NAME" --require-approval never "${context[@]}"

# ---- 3. Stack outputs -------------------------------------------------------------
output() {
  aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}
SITE_URL="$(output CloudFrontUrl)"
BUCKET="$(output BucketName)"
BACKEND_REPO="$(output BackendRepositoryUri)"
FRONTEND_REPO="$(output FrontendRepositoryUri)"
INSTANCE_ID="$(output InstanceId)"
DASHBOARD_URL="$(output DashboardUrl)"
REGISTRY="${BACKEND_REPO%%/*}"

# ---- 4. Images (arm64 for Graviton) -------------------------------------------
log "Building and pushing linux/arm64 images to $REGISTRY"
aws ecr get-login-password | docker login --username AWS --password-stdin "$REGISTRY"
# --provenance/--sbom off: push a plain image manifest (no attestation
# manifests showing up as untagged images in ECR and its lifecycle count).
build_push() { # build_push <repo-uri> <context-dir> [extra buildx args...]
  local repo=$1 dir=$2
  shift 2
  docker buildx build --platform linux/arm64 --provenance=false --sbom=false \
    -t "$repo:$IMAGE_TAG" -t "$repo:latest" --push "$@" "$dir"
}
build_push "$BACKEND_REPO" "$REPO_ROOT/backend"
build_push "$FRONTEND_REPO" "$REPO_ROOT/frontend" --build-arg NEXT_PUBLIC_API_BASE=/api/v1

# ---- 5. Model ---------------------------------------------------------------------
if [[ -n "$MODEL_PATH" ]]; then
  log "Uploading $MODEL_PATH to s3://$BUCKET/$MODEL_S3_KEY"
  aws s3 cp "$MODEL_PATH" "s3://$BUCKET/$MODEL_S3_KEY"
  sidecar="${MODEL_PATH%.onnx}.json"
  if [[ -f "$sidecar" ]]; then
    aws s3 cp "$sidecar" "s3://$BUCKET/${MODEL_S3_KEY%.onnx}.json"
  else
    echo "no sidecar $sidecar; the detector will use its default metadata"
  fi
fi

# ---- 6. Roll out on the instance via SSM Run Command -----------------------------
log "Waiting for $INSTANCE_ID to register with SSM"
ping=""
for _ in $(seq 1 60); do
  ping="$(aws ssm describe-instance-information \
    --filters "Key=InstanceIds,Values=$INSTANCE_ID" \
    --query 'InstanceInformationList[0].PingStatus' --output text 2>/dev/null || true)"
  [[ "$ping" == "Online" ]] && break
  sleep 10
done
[[ "$ping" == "Online" ]] || die "$INSTANCE_ID is not online in SSM (check the instance role and outbound access)"

log "Running /opt/trayagent/update.sh $IMAGE_TAG on $INSTANCE_ID"
# Wait for first-boot user data (cloud-init) before updating. IMAGE_TAG was
# validated above, so it is safe to embed in the command.
params="{\"commands\":[\"cloud-init status --wait >/dev/null || true\",\"/opt/trayagent/update.sh $IMAGE_TAG\"],\"executionTimeout\":[\"1200\"]}"
command_id="$(aws ssm send-command --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript --comment "TrayAgent deploy $IMAGE_TAG" \
  --parameters "$params" --query Command.CommandId --output text)"
status=Pending
for _ in $(seq 1 150); do
  sleep 10
  status="$(aws ssm get-command-invocation --command-id "$command_id" --instance-id "$INSTANCE_ID" \
    --query Status --output text 2>/dev/null || echo Pending)"
  case "$status" in Pending | InProgress | Delayed) continue ;; *) break ;; esac
done
aws ssm get-command-invocation --command-id "$command_id" --instance-id "$INSTANCE_ID" \
  --query '[StandardOutputContent, StandardErrorContent]' --output text | tail -n 40
[[ "$status" == "Success" ]] || die "update.sh on the instance ended with status $status"

# ---- 7. Public health check through CloudFront ----------------------------------
log "Waiting for $SITE_URL/api/health to report ok (up to ${HEALTH_TIMEOUT}s)"
deadline=$((SECONDS + HEALTH_TIMEOUT))
body=""
until [[ "$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status"))' 2>/dev/null)" == "ok" ]]; do
  ((SECONDS < deadline)) || die "health check did not report ok; last response: ${body:-<none>}"
  sleep 10
  body="$(curl -fsS --max-time 20 "$SITE_URL/api/health" 2>/dev/null || true)"
done
echo "$body"

# ---- 8. Done ------------------------------------------------------------------------
log "TrayAgent is live"
cat <<EOF
  App:        $SITE_URL
  Health:     $SITE_URL/api/health
  Dashboard:  $DASHBOARD_URL
  Image tag:  $IMAGE_TAG
  Seed demo:  scripts/aws/seed_demo.sh $SITE_URL
  Shell:      aws ssm start-session --target $INSTANCE_ID --region $AWS_REGION
EOF
