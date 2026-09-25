# TrayAgent: verified jewelry tray counts (OpenCV 5 agent on AWS Graviton)

A phone photo of a jewelry tray becomes a **verified** count. An agent runs OpenCV 5
tools in a bounded perception → decision → action loop. When the evidence is weak
(glare, blur, dense clusters, or a mismatch with the POS count), it chooses the next
step itself:
- request a specific re-shot;
- tile and zoom;
- compare with yesterday's approved photo;
- escalate to a human with annotated evidence.

No count that changes inventory is committed without a human.

- Spec: `docs/competition/SPEC.md` · Status: `docs/competition/STATUS.md` · Report: `docs/competition/TECHNICAL_REPORT.md` (+ PDF)
- Diagrams: `docs/competition/architecture.png`, `docs/competition/agent_workflow.png` (Graphviz sources in `docs/competition/diagrams/`)
- Trace demo: `docs/competition/trace_demo/TRACE_DEMO.md` · Decisions: `docs/competition/DECISIONS.md`

## Pinned runtime stack
| Component | Version |
|---|---|
| Python | 3.11 (`public.ecr.aws/docker/library/python:3.11-slim-bookworm`, multi-arch) |
| OpenCV | `opencv-python-headless==5.0.0.93` (DNN `ENGINE_AUTO`; YuNet face blur) |
| numpy | 2.2.6 |
| FastAPI / SQLAlchemy / Alembic | 0.115.0 / 2.0.32 / 1.13.2 |
| Detector | YOLOX (Apache-2.0) exported to ONNX, served by `cv2.dnn`; **no Ultralytics** (`scripts/license_gate.py`) |
| Frontend | Next.js 14.2.35, Node 20 (standalone image) |
| Database | PostgreSQL 16 |
| AWS | CDK `aws-cdk-lib==2.270.0` (CLI 2.1143.0): EC2 Graviton, ECR, S3, CloudWatch, CloudFront |

Full lists: `backend/requirements.txt`, `backend/requirements-dev.txt`, `frontend/package-lock.json`,
`training/requirements-yolox.txt`, `infra/aws/requirements.txt`.

## Build and test
```bash
make backend-venv                 # .venv with runtime + dev deps (OpenCV 5)
cd frontend && npm ci && cd ..
source .venv/bin/activate
make lint                         # ruff + black + eslint + license gate
make test                         # backend pytest + frontend vitest
make infra-venv && make infra-test infra-synth   # CDK unit tests + synth (no AWS credentials needed)
make image-multiarch              # backend image for linux/amd64 + linux/arm64
```

## Run locally (same containers as AWS)
```bash
cp .env.example .env
make up                           # postgres, minio, redis, backend, frontend, nginx
open http://localhost/scan        # mobile-first PWA; /api/health shows "opencv": "5.0.x"
```
Without trained weights, set `DETECTOR_BACKEND=classical` (the default in `.env.example`).
This is a labelled OpenCV baseline. With `onnx`, a missing model returns 503; nothing is ever silently mocked.

## Data → model → evaluation
See `training/README.md`: ingest (face blur) → OWLv2 pre-labels → CVAT review
(`docs/competition/LABELING_HOWTO.md`) → frozen 70/15/15 split → `training/train_yolox.py` →
`models/trayagent_v1.onnx` (SHA-256 via `scripts/fetch_model.sh`) → `make eval-agent` →
`reports/agentic/RESULTS.md`.

## Deploy to AWS
```bash
AWS_REGION=ap-southeast-1 MODEL_PATH=models/trayagent_v1.onnx scripts/aws/deploy.sh
scripts/aws/seed_demo.sh https://<cloudfront-domain>      # demo tenant POS figures
scripts/aws/teardown.sh                                   # removes everything (asks first)
```
Details, costs and troubleshooting: `infra/aws/README.md`.

## Demo video
`docs/competition/VIDEO_RUNBOOK.md` (`RECORD=1 BASE_URL=... demo/video/build.sh`).

---

# Legacy: VietJewelers Inventory Truth Layer (pre-competition README)


AI-assisted jewelry inventory audit system for tray photos, POS reconciliation, discrepancy resolution, and retraining feedback. The product direction is no longer just "count items in one image"; it is a visual evidence layer for catching stock variance before it becomes expensive shrink.

## Local production-like deployment (Docker Compose + Nginx)
1. `cp .env.example .env`
2. `make up`
3. `make bootstrap` (optional)
4. Access:
   - App: `http://localhost`
   - Backend health: `http://localhost/api/health`
   - MinIO console: `http://localhost:9001`

## Inventory truth layer workflow
- New audit scan API: `POST /api/v1/scans` uploads a tray image, runs AI counting, checks image quality, compares against expected/POS stock, and opens a discrepancy when counts differ.
- Review API: `PATCH /api/v1/scans/{id}/review` stores manual recounts and turns corrections into active-learning data for retraining.
- Discrepancy inbox: `GET /api/v1/discrepancies` and `POST /api/v1/discrepancies/{id}/resolve` manage stock variance through resolution.
- KiotViet pilot path:
  - `POST /api/v1/integrations/kiotviet/inventory-snapshots` imports POS stock snapshots.
  - `POST /api/v1/integrations/kiotviet/webhook` records webhook events idempotently.
  - `POST /api/v1/integrations/kiotviet/csv` imports CSV exports when API credentials are not ready.
  - `GET /api/v1/integrations/kiotviet/status` shows connector/snapshot health.
- Evidence images are served through `/api/v1/images/object/{path}` or short-lived URLs via `/api/v1/images/presigned`.

## Production-lite ship
- Release/versioning: `RELEASE.md`, `CHANGELOG.md`, `docs/release-checklist.md`
- Staging deploy guide: `docs/staging-deploy.md`
- Backup/restore guide: `docs/backup-restore.md`
- Operator runbook: `RUNBOOK.md`
- Incident response: `docs/incident-response.md`

### GHCR images
Published on SemVer tags by GitHub Actions:
- `ghcr.io/<owner>/aistockcounting-backend:<tag>`
- `ghcr.io/<owner>/aistockcounting-frontend:<tag>`

### Staging simulation (local)
```bash
docker compose --env-file .env.staging.example -f docker-compose.staging.yml up -d
./ops/smoke_test.sh
```

## Labeling workflow (CVAT + YOLO dataset)
1. Export images from DB/MinIO:
   - `make label-export-images LIMIT=5`
2. Start CVAT (local-only):
   - `cp .env.cvat.example cvat/.env.cvat`
   - `make cvat-up`
3. Create task from images:
   - `make cvat-create-task FOLDER=datasets/vj_items/images/all NAME="vj-items-smoke"`
4. Label in CVAT UI: `http://127.0.0.1:8081`
5. Export annotations:
   - `make cvat-export-yolo TASK_ID=<task_id> OUT_ZIP=datasets/vj_items/cvat_export.zip`
6. Split and validate:
   - `make dataset-split SEED=42`
   - `make dataset-validate`

## Training & model deployment
1. `make train-venv`
2. `make train-yolo`
3. `make eval-yolo RUN_DIR=outputs/vj_items/<run_dir>`
4. `make export-model VERSION=v0001 RUN_DIR=outputs/vj_items/<run_dir>`
5. Set `MOCK_MODE=false` and `MODEL_PT_PATH` / `MODEL_ONNX_PATH`.
6. `make model-smoke IMAGE=scripts/generated_sample.jpg`

## Key make targets
- Stack: `make dev`, `make up`, `make down`, `make logs`
- Staging: `make staging-up`, `make staging-down`, `make staging-smoke`
- Backups: `make backup-local`, `make restore-local`
- CVAT/Data/Training: as listed in Makefile
- Quality: `make lint`, `make test`

## Environment templates
- Local dev: `.env.example`
- Staging: `.env.staging.example`
- Production-lite: `.env.prod.example`
- CVAT: `.env.cvat.example` -> `cvat/.env.cvat`
- KiotViet connector envs: `KIOTVIET_CLIENT_ID`, `KIOTVIET_CLIENT_SECRET`, `KIOTVIET_RETAILER`; leave blank to use CSV fallback.
- Multi-tenant pilot key: `DEFAULT_TENANT_KEY` and optional `X-TENANT-KEY` request header.

## Operability notes
- `/api/health` checks DB + MinIO reachability.
- Nginx includes basic security headers.
- Configure Docker daemon log rotation on server, e.g. `max-size=10m`, `max-file=5`.
