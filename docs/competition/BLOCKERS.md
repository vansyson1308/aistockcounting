# Blockers

| ID | Opened | Blocker | Impact | Workaround in place | Owner action |
|---|---|---|---|---|---|
| B-001 | 2026-09-25 | No real tray photos in `datasets/vj_items/raw/`. | No training, no real metrics, no demo trays. The submission is NOT ready without them. | Procedural synthetic fixtures (`backend/tests/fixtures/`) are used **only in tests**. The labeling, training and eval tooling is built and tested on them. | Add ≥150 photos (≈30 hard cases), 3 "yesterday vs today" pairs and demo trays A/B/C. See Checkpoint A in STATUS.md. |
| B-002 | 2026-09-25 | No AWS credentials or region. | Cannot deploy to Graviton, ECR, S3 or CloudWatch, and cannot measure Graviton latency. | The same containers run locally with docker compose (MinIO standing in for S3). The CDK app is written and `cdk synth`-tested. | Provide credentials (an IAM user or SSO profile) and a region (`ap-southeast-1` suggested). |
| B-003 | 2026-09-25 | `docs/competition/SPEC.md` was missing. | The policy thresholds and gates had to be defined by us. | Authored from the brief (DECISIONS D-001). | Review SPEC §3, §4.4 and §7. |
| B-004 | 2026-09-25 | Removing the football-pivot directories needs approval. | They stay in the tree (D-003). | None needed for runtime. | Approve or decline (Checkpoint A item 3). |
