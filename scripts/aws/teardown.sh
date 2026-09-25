#!/usr/bin/env bash
# Remove the TrayAgent AWS deployment: empty the evidence bucket (every object
# version and delete marker), delete the ECR images, then `cdk destroy`.
#
# Usage:
#   scripts/aws/teardown.sh          # asks for confirmation
#   scripts/aws/teardown.sh --yes    # no prompt
#
# Environment: AWS_REGION (default ap-southeast-1), STACK_NAME (default TrayAgent).
# Resources deployed with -c retainData=true are emptied here but kept by
# CloudFormation; the CDK bootstrap stack (CDKToolkit) is never touched.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INFRA_DIR="$REPO_ROOT/infra/aws"
export AWS_REGION="${AWS_REGION:-ap-southeast-1}"
export AWS_DEFAULT_REGION="$AWS_REGION"
STACK_NAME="${STACK_NAME:-TrayAgent}"

assume_yes=false
case "${1:-}" in
  --yes | -y) assume_yes=true ;;
  "") ;;
  *) echo "usage: $0 [--yes]" >&2; exit 2 ;;
esac

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
for tool in aws node python3; do command -v "$tool" >/dev/null || die "'$tool' is required"; done
account="$(aws sts get-caller-identity --query Account --output text)" || die "no AWS credentials"

output() {
  aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}
aws cloudformation describe-stacks --stack-name "$STACK_NAME" >/dev/null 2>&1 ||
  die "stack $STACK_NAME not found in $AWS_REGION (account $account)"
bucket="$(output BucketName)"
repos=("$(output BackendRepositoryUri)" "$(output FrontendRepositoryUri)")
site="$(output CloudFrontUrl)"

cat <<EOF
This permanently deletes, in account $account / $AWS_REGION:
  - stack $STACK_NAME ($site): EC2 host with its Postgres data, VPC, CloudFront,
    alarms, dashboard, SNS topic, SSM parameters, log group
  - every object version in s3://$bucket
  - every image in ${repos[0]##*/} and ${repos[1]##*/}
EOF
if [[ "$assume_yes" != true ]]; then
  read -r -p "Type the stack name ($STACK_NAME) to continue: " answer
  [[ "$answer" == "$STACK_NAME" ]] || die "aborted"
fi

# S3: delete versions and delete markers, up to 1000 per call, until empty.
echo "==> Emptying s3://$bucket"
deleted=0
for kind in Versions DeleteMarkers; do
  while true; do
    objects="$(aws s3api list-object-versions --bucket "$bucket" --max-items 1000 --output json \
      --query "${kind}[].{Key: Key, VersionId: VersionId}")"
    count="$(printf '%s' "$objects" | python3 -c 'import json,sys; print(len(json.load(sys.stdin) or []))')"
    ((count > 0)) || break
    batch="{\"Objects\": $objects, \"Quiet\": true}"
    aws s3api delete-objects --bucket "$bucket" --delete "$batch" >/dev/null
    deleted=$((deleted + count))
  done
done
echo "    removed $deleted object versions / delete markers"

# ECR: CloudFormation empties the repositories itself (emptyOnDelete) unless
# they are retained; deleting the images here covers both cases.
for uri in "${repos[@]}"; do
  repo="${uri##*/}"
  ids="$(aws ecr list-images --repository-name "$repo" --query imageIds --output json)"
  n="$(printf '%s' "$ids" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')"
  if ((n > 0)); then
    # batch-delete-image takes at most 100 ids per call.
    printf '%s' "$ids" | python3 -c '
import json, sys
ids = json.load(sys.stdin)
for i in range(0, len(ids), 100):
    print(json.dumps(ids[i:i + 100]))' | while read -r chunk; do
      aws ecr batch-delete-image --repository-name "$repo" --image-ids "$chunk" >/dev/null
    done
  fi
  echo "==> Deleted $n image(s) from $repo"
done

echo "==> cdk destroy $STACK_NAME"
[[ -x "$INFRA_DIR/.venv/bin/python" ]] || die "infra/aws/.venv is missing; see infra/aws/README.md"
[[ -x "$INFRA_DIR/node_modules/.bin/cdk" ]] || (cd "$INFRA_DIR" && npm ci --no-audit --no-fund)
(cd "$INFRA_DIR" && ./node_modules/.bin/cdk destroy "$STACK_NAME" --force \
  -c "stackName=$STACK_NAME" -c "region=$AWS_REGION")

echo "==> Removed stack $STACK_NAME, the contents of s3://$bucket and the ECR images."
if aws s3api head-bucket --bucket "$bucket" >/dev/null 2>&1; then
  echo "    Kept (retainData=true): bucket $bucket, the ECR repositories and the log group."
fi
echo "    The CDK bootstrap stack CDKToolkit is shared and was left in place."
