# Incident Response (MVP)

## Severity
- **SEV-1:** Full outage/data loss risk.
- **SEV-2:** Core flow degraded (upload/save/history).
- **SEV-3:** Minor UX or non-critical issue.

## Triage checklist
1. Confirm scope and start time.
2. Check `docker compose ps` and `docker compose logs`.
3. Run `ops/smoke_test.sh`.
4. Preserve logs/snapshots before restart.

## Data-loss prevention
- Stop destructive actions.
- Trigger immediate `backup_all.sh` if storage still reachable.
- Prefer restore to clone/staging for validation first.

## When to restore
- Corrupt DB/object data.
- Accidental deletion not recoverable from app.
- Failed migration with inconsistent data.

## Postmortem template
- Timeline
- Root cause
- Customer impact
- Detection gaps
- Corrective actions
- Follow-up owner + due date
