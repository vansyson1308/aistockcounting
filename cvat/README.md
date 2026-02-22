# Local CVAT (internal use only)

> ⚠️ Safety: CVAT is bound to `127.0.0.1` only by default. Do **not** expose publicly.

## 1) Prepare credentials
1. Copy env template:
   - `cp .env.cvat.example .env.cvat`
2. Edit `.env.cvat` with local credentials.

## 2) Start CVAT
- From repo root: `make cvat-up`
- Or inside folder: `cd cvat && docker compose --env-file .env.cvat up -d`

## 3) Access UI
- UI: `http://127.0.0.1:8081`
- API/server: `http://127.0.0.1:8080`

## 4) Admin user flow
- CVAT server bootstraps with the values in `.env.cvat` (`CVAT_USER`, `CVAT_PASS`) through env + startup script.
- If needed, create superuser manually:
  - `docker compose exec cvat_server python3 manage.py createsuperuser`

## 5) Logs / stop / cleanup
- Logs: `make cvat-logs`
- Stop: `make cvat-down`
- Remove volumes: `cd cvat && docker compose down -v`

## 6) Notes
- This setup is intended for local/internal labeling only.
- Persisted data is stored in named Docker volumes.
