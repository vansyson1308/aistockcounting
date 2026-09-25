# TrayAgent — competition status

Last updated: 2026-09-25 (Phase 1 complete)
Branch: `claude/relaxed-wozniak-nhlyvm` (acts as `opencv-comp`; see DECISIONS D-002)
Deadline: 2026-10-26 23:59 PT · Code freeze target: 2026-10-22

## Checklist

- [x] Phase 0: setup and recon
- [x] Phase 1: OpenCV 5 migration
- [ ] Phase 2: data and model (tooling first; training waits on photos)
- [ ] Phase 3: OpenCV 5 tool library
- [ ] Phase 4: agent (controller, planner, trace, routes)
- [ ] Phase 5: frontend (timeline, review page)
- [ ] Phase 6: AWS deployment (CDK, deploy/teardown)
- [ ] Phase 7: evaluation on the frozen real test set
- [ ] Phase 8: COOL (stretch)
- [ ] Phase 9: submission materials
- [ ] Phase 10: demo video pipeline

## Phase 0 recon: facts confirmed (2026-09-25)

| Claim in the brief | Verified | Evidence |
|---|---|---|
| `InferenceService` silently falls back to mock | Yes | `backend/app/services/inference.py`: `mock_mode` defaults to `True`; with no model it logs a warning and returns hash-seeded fake boxes. |
| Quality checks are PIL-based | Yes | `backend/app/utils/image_quality.py` uses `ImageStat` and `FIND_EDGES`. |
| No weights, no images | Yes | `/models/` is git-ignored and empty; `datasets/vj_items/images/*` hold only `.gitkeep`; `datasets/vj_items/raw/` does not exist. |
| No AWS infra | Yes | `infra/` contains only `db/init/001_extensions.sql`. |
| Storage layer uses boto3 | Yes | `backend/app/services/storage.py` uses `boto3.client("s3", endpoint_url=MinIO)`. |
| Ultralytics in the runtime | Yes | `backend/requirements.txt` pins `ultralytics==8.3.0` (grandfathered in the license gate). |

Baseline before any change: backend `pytest` 42 passed; frontend `vitest` 18 passed;
`ruff` clean; `next lint` clean. The Docker daemon starts in this container
(`dockerd`); `ffmpeg`, `aws` and `cdk` are not installed.

## OWNER CHECKPOINT A (open; work continues meanwhile)

1. At least 150 real tray photos in `datasets/vj_items/raw/`, with varied
   light and angles and about 30 hard cases (glare, blur, dense). Also 3
   "yesterday vs today" pairs of the same tray (name them
   `pairs/<tray>_prev.jpg` and `pairs/<tray>_curr.jpg`), and demo trays
   `demo/A_clean.jpg`, `demo/B_glare.jpg`, `demo/B_reshot.jpg`,
   `demo/C_dense.jpg` and `demo/C_prev.jpg`, with the POS count for C.
2. AWS credentials and a region (`ap-southeast-1` suggested).
3. Approval to remove `ml/`, `reports/gate0a/` and `tools/camsim/` from this
   branch only.
4. Will judges get repo access, or a source archive?

## Phase 1: done (2026-09-25)

- `opencv-python-headless==5.0.0.93` pinned; `ultralytics` and `onnxruntime` removed from
  the runtime; the license gate now refuses any grandfathering of runtime manifests.
- `backend/app/utils/image_quality.py`: rewritten in cv2 (Laplacian variance inside the
  eroded tray, HSV glare ratio, p99 brightness, histogram clipping, tray coverage),
  with the same `ImageQuality(score, flags, metrics)` shape.
- `backend/app/services/detector_cv.py`: YOLOX ONNX through `cv2.dnn.readNetFromONNX`
  (engine AUTO/NEW/CLASSIC), letterbox, grid decode and `cv2.dnn.NMSBoxes`; an OpenCV
  classical baseline; an explicit mock.
- Mock is explicit only. A missing model gives `detector.ready=false` in `/health` and
  HTTP 503 `DETECTOR_UNAVAILABLE`, never fake boxes.
- `/health` and `/api/health` expose `opencv` (5.0.0) and the detector status.
- Multi-arch Dockerfile: amd64 and arm64 both built; the arm64 image ran under QEMU
  and `/health` returned `opencv 5.0.0` on `aarch64`.
- Faces blurred before storage (YuNet via `cv2.FaceDetectorYN`).
- Alembic fixed (async env) and migration 0004 (`agent_steps`, scan agent/approval
  columns) verified on Postgres 16.
- `make lint` green; `make test`: backend 86 passed / 1 skipped, frontend 18 passed.

## Next

Phase 3 tool library and Phase 4 agent (Phase 2 tooling runs in parallel: waiting on photos).

## Blockers

See `BLOCKERS.md` (B-001 photos, B-002 AWS, B-003 spec authored, B-004 football dirs).

## Unverified

- No accuracy, Graviton latency or COOL numbers exist yet.
- Engineering note (not a result): on this x86 dev container, a COCO YOLOX-nano ONNX
  forward at 416×416 took about 12 ms with `ENGINE_NEW` and about 26 ms with
  `ENGINE_CLASSIC` (5 runs, after warm-up). This will be re-measured properly in Phase 7/8.
