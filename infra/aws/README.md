# TrayAgent on AWS (CDK, Python)

Infrastructure as code for SPEC §6: one EC2 **Graviton** host running the
TrayAgent containers, behind **CloudFront** for HTTPS, with **S3** evidence
storage, **ECR** images and **CloudWatch** logs, metrics, dashboard and alarms.

```
viewer ──HTTPS──▶ CloudFront (*.cloudfront.net cert, redirect to HTTPS, no caching)
                     │  HTTP :80, only from the CloudFront origin-facing prefix list
                     ▼
        EC2 t4g.large (arm64, AL2023, Elastic IP, public subnet, no NAT, no SSH)
        docker compose:  nginx ─▶ frontend (Next.js :3000)
                               └▶ backend (FastAPI + OpenCV 5 + agent :8000) ─▶ postgres:16
                     │                         │
      awslogs driver ▼                         ▼ instance role
      CloudWatch Logs (14 days)     S3 evidence bucket · CloudWatch metrics (TrayAgent)
                                    · ECR pull · Bedrock (optional)
```

| File | Purpose |
|---|---|
| `app.py`, `trayagent_stack.py` | CDK app and stack (all settings via `-c` context) |
| `cdk.json`, `package.json` | CDK feature flags; pinned CDK CLI (`aws-cdk@2.1143.0`) |
| `requirements*.txt` | pinned `aws-cdk-lib==2.270.0`, `constructs`, test tools |
| `tests/` | template assertions and a stubbed run of the host script |
| `../../deploy/aws/` | `user-data.sh`, `update.sh`, `docker-compose.aws.yml` for the host |
| `../../nginx/nginx.aws.conf` | nginx behind CloudFront |
| `../../scripts/aws/` | `deploy.sh`, `teardown.sh`, `seed_demo.sh` |

## What gets created

- **VPC** with two public subnets, an internet gateway and **no NAT gateway**.
- **EC2** `t4g.large` (or `c7g.large`), latest Amazon Linux 2023 **arm64** AMI
  (SSM parameter resolved by CloudFormation), 30 GB encrypted gp3 root volume,
  IMDSv2 only (hop limit 2 so containers get role credentials), Elastic IP.
- **Security group**: inbound TCP 80 from the CloudFront origin-facing managed
  prefix list only. No port 22. Shell access uses SSM Session Manager.
- **CloudFront**: origin = the EC2 public DNS name of the Elastic IP, HTTP only,
  60 s read timeout, viewer redirect to HTTPS, `CachingDisabled` +
  `AllViewer` (the viewer's Host header must reach Next.js; see the comment in
  the stack), all methods. `/_next/static/*` is cached (content-hashed files).
- **S3** evidence bucket: all public access blocked, SSE-S3, TLS-only policy,
  versioned. `uploads/`, `thumbnails/`, `evidence/` expire after 30 days;
  noncurrent versions after 7 days; incomplete multipart uploads aborted after 7.
- **ECR** `trayagent-backend`, `trayagent-frontend`: scan on push, keep the last
  10 images.
- **IAM instance role**: `AmazonSSMManagedInstanceCore`, ECR pull on both repos,
  S3 read/write/delete on the bucket, `cloudwatch:PutMetricData` limited to the
  `TrayAgent` namespace, log writes to the log group, read on its SSM
  parameters, and `bedrock:InvokeModel` only with `enableBedrock=true`.
- **CloudWatch**: log group `/trayagent/<stack>` (14 days), dashboard
  (runs, steps, escalation and recapture rate, latency p50/p95, planner
  fallbacks, CPU), alarms to an SNS topic:
  escalation rate > 50 % over 1 h (evaluated only with ≥ 5 runs, missing data
  = OK), `AgentLatencyMs` p95 > 15 000 ms over 15 min, EC2 status check failed.
- **SSM parameters** `/trayagent/<stack>/{app-env,compose,nginx,update-sh}`:
  the host's desired state (no secrets).
- Small CDK-managed Lambdas for: the prefix-list lookup, emptying the bucket on
  delete, and removing the default security group's rules.

### How the host is configured

User data (`deploy/aws/user-data.sh`) runs once. It installs Docker and the
compose v2 plugin (aarch64 release binary, SHA-256 checked), generates the
Postgres password with `openssl rand` into the root-only
`/opt/trayagent/secrets.env` (never in the template), installs
`/opt/trayagent/update.sh` from SSM and runs it.

`update.sh [IMAGE_TAG]` is the only deploy mechanism on the host. Each run it
refreshes itself and the compose file, nginx config and `app.env` from SSM,
syncs the ONNX model from S3 (when `modelS3Key` is set), logs in to ECR, pulls
and runs `docker compose up -d --wait`. Because everything is re-read from SSM,
a `cdk deploy` followed by `update.sh` applies any configuration change
without replacing the instance or its Postgres data.

On the very first deploy the instance boots before any image is in ECR, so
that first `update.sh` fails at the pull (logged, tolerated); `deploy.sh`
pushes the images and then runs `update.sh` through SSM Run Command.

## Prerequisites

- AWS account and credentials for the AWS CLI v2 (`aws sts get-caller-identity`).
- Docker with **buildx**. On an x86 machine, enable arm64 emulation once:
  `docker run --privileged --rm tonistiigi/binfmt --install arm64`.
- Node.js 18+ (for the pinned CDK CLI) and Python 3.11+.
- Optional: the [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html) for `aws ssm start-session`.

## Deploy

```bash
scripts/aws/deploy.sh                                   # t4g.large in ap-southeast-1
ALARM_EMAIL=you@example.com scripts/aws/deploy.sh       # + alarm emails (confirm the SNS mail)
MODEL_PATH=models/trayagent_v1.onnx scripts/aws/deploy.sh   # upload weights, DETECTOR_BACKEND=onnx
INSTANCE_TYPE=c7g.large IMAGE_TAG=v1 scripts/aws/deploy.sh
scripts/aws/seed_demo.sh https://dxxxxxxxxxxxx.cloudfront.net   # demo tenant + TRAY-A/B/C
```

`deploy.sh` is idempotent. It runs `cdk bootstrap`, `cdk deploy`, builds and
pushes `linux/arm64` images tagged `IMAGE_TAG` (default: git short SHA) and
`latest`, uploads the model, runs `update.sh` on the instance via SSM, polls
`https://<cloudfront>/api/health` until `"status": "ok"` and prints the URL.
All options are documented in the script header. The first deploy takes
roughly 10–20 minutes (CloudFront creation plus image builds).

Without `MODEL_PATH`/`MODEL_S3_KEY` the backend runs the OpenCV classical
baseline (`DETECTOR_BACKEND=classical`), labelled as such in `/health`. To keep
using a model uploaded earlier, pass `MODEL_S3_KEY=models/trayagent_v1.onnx`.

Redeploy only the application (no infrastructure change):

```bash
aws ssm send-command --instance-ids <InstanceId> --document-name AWS-RunShellScript \
  --parameters 'commands=["/opt/trayagent/update.sh <tag>"]'
```

### Manual CDK usage

```bash
cd infra/aws
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
npm ci
npx cdk synth                                  # no AWS credentials needed
npx cdk diff  -c instanceType=c7g.large        # needs credentials
npx cdk deploy -c alarmEmail=you@example.com
```

| Context key | Default | Meaning |
|---|---|---|
| `stackName` | `TrayAgent` | stack name (also names the log group, dashboard, SSM path) |
| `region` | `ap-southeast-1` | target region |
| `instanceType` | `t4g.large` | any `t4g.*` / `c7g.*` size; other families are rejected |
| `enableBedrock` | `false` | Bedrock planner + `bedrock:InvokeModel` |
| `bedrockModelId` | – | model or inference-profile id (required with Bedrock) |
| `alarmEmail` | – | email subscription on the alarm topic |
| `modelS3Key` | – | ONNX key in the bucket; switches the detector to `onnx` |
| `retainData` | `false` | keep bucket, ECR repos and log group on destroy |
| `cloudFrontPrefixListId` | looked up | skip the deploy-time prefix-list lookup |
| `amiId` | latest AL2023 arm64 | pin the AMI (see *Known limitations*) |
| `defaultTenantKey` | `demo` | `DEFAULT_TENANT_KEY` of the backend |

## Tests

```bash
cd infra/aws
.venv/bin/python -m pytest -q      # template assertions + update.sh with stubbed aws/docker
npx cdk synth --quiet              # full synth, no credentials required
```

## Enable Bedrock

1. In the Bedrock console, enable access to the model you want in the region.
2. Deploy with the planner switched on (an inference profile id works too):

   ```bash
   ENABLE_BEDROCK=true BEDROCK_MODEL_ID=<model-or-inference-profile-id> scripts/aws/deploy.sh
   ```

This sets `AGENT_PLANNER=bedrock` and grants `bedrock:InvokeModel` (what the
Converse API is authorised as) on foundation models and inference profiles.
If Bedrock fails at run time the backend falls back to the deterministic
planner and counts it in the `PlannerFallbacks` metric. Deploy again with
`ENABLE_BEDROCK=false` to remove the permission.

## Restricting access

- **Origin**: already closed. Port 80 accepts only CloudFront's origin-facing
  IP ranges and there is no SSH; the admin path is IAM + SSM.
- **Viewers**: the site is public by design (demo). To limit it, add a
  CloudFront geo restriction (`geo_restriction=cloudfront.GeoRestriction.allowlist("VN")`
  on the `Distribution`) or attach an AWS WAF web ACL with an IP allow-list
  (`web_acl_id=...`; WAF for CloudFront lives in us-east-1 and has a monthly
  cost). For an app-level token, the backend supports `ENABLE_SIMPLE_AUTH` /
  `SIMPLE_AUTH_TOKEN`; add them to `app_env` in the stack and to the backend
  `environment` in `deploy/aws/docker-compose.aws.yml`.
- **Data**: the bucket is private and TLS-only; the instance role is scoped to
  this bucket, these two repositories and the `TrayAgent` metric namespace.

## Teardown

```bash
scripts/aws/teardown.sh          # asks you to type the stack name
scripts/aws/teardown.sh --yes
```

It empties the bucket (all versions and delete markers), deletes the ECR
images, runs `cdk destroy --force` and prints what was removed. The shared
`CDKToolkit` bootstrap stack is left in place (`aws cloudformation delete-stack
--stack-name CDKToolkit` removes it if nothing else uses it).

## Cost (rough estimates, not quotes)

These are ballpark on-demand figures from memory, **not looked up**; prices
vary by region and change over time. Check the AWS Pricing Calculator for
`ap-southeast-1` before relying on them.

| Item | Estimate |
|---|---|
| EC2 `t4g.large` on demand | ~US$0.07–0.09 per hour (~US$50–65 per month running 24/7). `c7g.large` is in the same range. T4g runs in *unlimited* credit mode by default: sustained high CPU adds a surplus-credit charge. Stop the instance when idle. |
| EBS gp3 30 GB | ~US$2.5–3.5 per month |
| Public IPv4 (Elastic IP) | ~US$0.005 per hour (~US$3.6 per month) |
| CloudFront | Free tier covers demo traffic (1 TB out and 10 M requests per month); EC2 → CloudFront transfer is free |
| S3 | Cents per month at demo volume (objects expire after 30 days) |
| CloudWatch | 3 alarms and 1 dashboard are within the free tier (10 alarms, 3 dashboards); ~6 custom metrics ≈ US$0.30 each per month beyond the free 10; log ingestion ≈ US$0.50–0.70 per GB |
| ECR | ~US$0.10 per GB-month (10 images kept per repo) |
| Bedrock (optional) | per token, model dependent |
| SSM, IAM, SNS email | free at this volume |

No NAT gateway (≈ US$30+ per month) and no load balancer (≈ US$16+ per month)
are used, on purpose.

## Troubleshooting

- **Shell on the host** (no SSH):
  `aws ssm start-session --target <InstanceId> --region ap-southeast-1`, then
  `sudo -i && cd /opt/trayagent`.
- **Containers**: `docker compose ps`, `docker compose logs -f backend`
  (inside `/opt/trayagent`); re-run `./update.sh` to redeploy.
- **Logs without a shell**: `aws logs tail /trayagent/TrayAgent --follow`
  (one stream per container name).
- **First boot**: `/var/log/trayagent-bootstrap.log` and
  `/var/log/cloud-init-output.log`.
- **CloudFront 502/504**: the containers are down or unhealthy
  (`docker compose ps`), or the security group has no prefix-list rule. The
  CloudFront prefix list counts as ~55 rules against the default 60-rule
  security-group quota; do not add many more rules to this group.
- **`/api/health` says `degraded`**: `checks` shows which of db / S3 /
  detector failed. `detector: false` with `DETECTOR_BACKEND=onnx` means the
  model file or its sidecar is missing in `/opt/trayagent/models`.
- **`exec format error`** in a container: the image was built for amd64. Build
  with `--platform linux/arm64` (deploy.sh does) after installing binfmt.
- **No alarm emails**: confirm the SNS subscription email first.
- **SSM command stuck in Pending**: the instance is not registered; check
  `aws ssm describe-instance-information` and that it has outbound internet.

## Known limitations

- Single instance, single AZ: fine for a demo, not highly available. Postgres
  lives on the instance's root volume; S3 evidence survives instance loss.
- The AMI comes from the "latest AL2023 arm64" SSM parameter. When AWS
  publishes a new AMI, the next `cdk deploy` **replaces the instance** (and its
  Postgres data). Pin it with `-c amiId=ami-...` for a long-lived demo.
- Changing `deploy/aws/user-data.sh` has no effect on a running instance
  (user data runs once); everything else is applied by `update.sh`.
