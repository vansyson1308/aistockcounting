# Release Checklist

## Preflight
- [ ] `CHANGELOG.md` updated.
- [ ] All CI checks green.
- [ ] `.env.staging` validated (no blank required values).
- [ ] Latest backup exists and restore drill status is known.

## Smoke tests
- [ ] `/api/health` returns `ok` with DB/MinIO reachable.
- [ ] Frontend home page loads via Nginx.
- [ ] Upload -> count -> save -> history -> stats basic flow verified.

## Rollback readiness
- [ ] Previous image tags available.
- [ ] Previous `.env` and compose snapshot retained.
- [ ] Rollback command prepared.

## Backup checks
- [ ] `ops/backup/backup_all.sh` run recently.
- [ ] Backup manifest includes sha256 checksums.
- [ ] `ops/backup/prune_backups.sh` retention configured.
