# Release Process (SemVer)

Current release line: `v0.1.x`.

## 1) Pre-release
1. Ensure CI passes on `main`.
2. Update `CHANGELOG.md` under a new version section.
3. Run local checks:
   - `make lint`
   - `make test`

## 2) Tag release
```bash
git checkout main
git pull --ff-only
git tag v0.1.0
git push origin v0.1.0
```

## 3) Build/publish images
Tag push triggers `.github/workflows/docker-publish.yml` to publish:
- `ghcr.io/<owner>/aistockcounting-backend:v0.1.0`
- `ghcr.io/<owner>/aistockcounting-frontend:v0.1.0`
- `...:<git-sha>`

## 4) Deploy staging
Run workflow `deploy-staging` or SSH to server and run:
```bash
cd /opt/vj-inventory/current
./ops/deploy_staging.sh
```

## 5) Post-release verification
- Run `ops/smoke_test.sh` on staging.
- Record release notes and rollback point.
