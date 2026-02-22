# RUNBOOK (Operator)

## Start/stop
- Start: `make up`
- Stop: `make down`
- Logs: `make logs`

## Deploy/update
- Preferred: GitHub Action `deploy-staging`
- Manual: `./ops/deploy_staging.sh`

## Rollback
- `./ops/deploy_staging.sh rollback`
- Or set previous image tags in `.env` then redeploy.

## Backup/restore
- Backup: `./ops/backup/backup_all.sh`
- Restore Postgres: `./ops/backup/restore_postgres.sh <dump>`
- Restore MinIO: `./ops/backup/restore_minio.sh <tar.gz>`

## Known failure modes
- DB down: check `db` health/logs, credentials, disk.
- MinIO credential mismatch: align `.env` `MINIO_*` and restart backend/minio.
- Nginx misroute: verify `nginx/nginx.conf` upstream names and container health.
- Model load fails: set `MOCK_MODE=true` and restart backend.
- Disk full: prune backups/images and old Docker artifacts.
