# VietJewelers Inventory Truth Layer

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
