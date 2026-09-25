#!/bin/bash
# /opt/trayagent/update.sh [IMAGE_TAG]  (run as root)
#
# (Re)deploys TrayAgent on the EC2 host. Idempotent; safe to run any time.
#  1. Fetches the desired state that CDK rendered into SSM Parameter Store
#     (this script, app.env, docker-compose.yml, nginx.conf), so a `cdk deploy`
#     change never needs the instance to be replaced. When this script itself
#     changed, it installs the new version and re-executes it.
#  2. Syncs the ONNX model from S3 when MODEL_S3_KEY is set; otherwise, or if
#     the download fails, the backend runs the OpenCV classical baseline.
#  3. Logs in to ECR, pulls and restarts the containers, then waits until
#     every container is healthy.
# The first boot runs it before any image has been pushed; that run fails at
# the pull and scripts/aws/deploy.sh runs it again after pushing the images.
#
# CDK stores this file in SSM with comment lines stripped (4 KB limit).
set -euo pipefail
cd "${TRAYAGENT_DIR:-/opt/trayagent}" # overridable for tests only
# shellcheck source=/dev/null
source ./instance.env # AWS_REGION, PARAM_PREFIX (written by user data)
umask 077

# One run at a time (deploys via SSM can overlap with a manual run). The lock
# fd and TRAYAGENT_LOCKED survive the self-update exec below.
if [[ -z "${TRAYAGENT_LOCKED:-}" ]]; then
  exec 9>.update.lock
  flock -w 900 9 || { echo "another update.sh is still running" >&2; exit 1; }
  export TRAYAGENT_LOCKED=1
fi

param() {
  aws ssm get-parameter --region "$AWS_REGION" --name "$PARAM_PREFIX/$1" \
    --query Parameter.Value --output text >"$2.tmp"
  mv "$2.tmp" "$2"
}

if [[ -z "${TRAYAGENT_SELF_UPDATED:-}" ]]; then
  param update-sh update.sh.new
  if ! cmp -s update.sh.new update.sh; then
    install -m 700 update.sh.new update.sh
    rm -f update.sh.new
    TRAYAGENT_SELF_UPDATED=1 exec ./update.sh "$@"
  fi
  rm -f update.sh.new
fi

if [[ $# -gt 0 ]]; then
  [[ "$1" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]] || { echo "bad image tag: $1" >&2; exit 2; }
  echo "IMAGE_TAG=$1" >image.env
fi
[[ -f image.env ]] || echo "IMAGE_TAG=latest" >image.env

param app-env app.env
param compose docker-compose.yml
param nginx nginx.conf
chmod 644 nginx.conf
# shellcheck source=/dev/null
source ./app.env

# Model weights: s3://$S3_BUCKET/$MODEL_S3_KEY and its sidecar (<name>.json).
detector="$DETECTOR_BACKEND"
if [[ -n "${MODEL_S3_KEY:-}" ]]; then
  if aws s3 cp --region "$AWS_REGION" --only-show-errors \
    "s3://$S3_BUCKET/$MODEL_S3_KEY" models/trayagent_v1.onnx.tmp; then
    mv models/trayagent_v1.onnx.tmp models/trayagent_v1.onnx
    aws s3 cp --region "$AWS_REGION" --only-show-errors \
      "s3://$S3_BUCKET/${MODEL_S3_KEY%.onnx}.json" models/trayagent_v1.json ||
      echo "no model sidecar in S3; the detector uses its defaults"
  elif [[ ! -f models/trayagent_v1.onnx ]]; then
    echo "WARNING: s3://$S3_BUCKET/$MODEL_S3_KEY not found; using the classical detector" >&2
    detector=classical
  fi
  chmod -R a+rX models
fi

cat app.env secrets.env image.env >.env
sed -i "s/^DETECTOR_BACKEND=.*/DETECTOR_BACKEND=$detector/" .env

aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "$ECR_REGISTRY" >/dev/null
docker compose pull --quiet
docker compose up -d --remove-orphans --wait --wait-timeout 300
docker image prune -f >/dev/null
docker compose ps
echo "TrayAgent is up: $(grep ^IMAGE_TAG image.env), DETECTOR_BACKEND=$detector"
