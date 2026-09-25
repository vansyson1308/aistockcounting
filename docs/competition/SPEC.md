# TrayAgent — Product Spec (OpenCV AI Competition 2026, powered by AWS)

> Provenance: this file did not exist when the competition work started
> (2026-09-25). It was written from the owner's mission brief and the existing
> PRD / truth-layer code. See `DECISIONS.md` D-001. When code reality and this
> spec disagree, reality wins and the deviation is logged in `DECISIONS.md`.

## 1. Problem

Jewelry stores count every display tray daily. Today staff photograph a tray,
count by eye, write the number on the photo, post it to a chat group and type
it into a sheet. The work is slow and error-prone, and it misses shrink: a
missing ring is found days later, if at all.

A single-shot detector does not fix this. Jewelry trays are hard for vision:
specular glare, motion blur from handheld phones, dense clusters of small
items and look-alike empty slots. A wrong automatic count is worse than no
count, because it quietly changes inventory.

## 2. Users

- **Store staff** (primary): photograph trays on a phone and follow re-shoot
  instructions. They are not technical.
- **Store manager / auditor**: approves, corrects or rejects counts the agent
  escalates, using the annotated evidence.
- **Owner**: reads discrepancy value and trends.

## 3. MVP scope (must ship)

- [ ] M1. Phone photo → count through an OpenCV 5 pipeline (DNN detector on an
      ONNX model, served by `cv2.dnn`).
- [ ] M2. OpenCV 5 tool library: `assess_quality`, `rectify_tray`, `detect`,
      `tile_detect`, `zoom_recount`, `reduce_glare`, `compare_previous`,
      `render_evidence` (pure functions, typed I/O, evidence images).
- [ ] M3. Agent: a bounded perception → decision → action loop (§4), where the
      OpenCV output decides the next tool, a re-shot request or a human
      escalation.
- [ ] M4. Human approval gate: no count that changes inventory is committed
      without a human decision (§8).
- [ ] M5. Full trace per scan (tool, inputs, outputs, evidence key, decision,
      reason, latency) in `agent_steps`, plus an `AuditEvent` per decision.
- [ ] M6. Mobile-first web UI: live agent timeline, re-shot instructions and
      a review page (before/after, uncertain regions, diff heatmap,
      approve / correct / reject).
- [ ] M7. Runs on AWS Graviton (arm64) with S3 evidence storage and
      CloudWatch logs, metrics and alarms.
- [ ] M8. Honest evaluation on a frozen real test set, with failure cases.

Out of scope: SKU recognition, weight or karat estimation, and POS write-back.

## 4. Agent design

### 4.1 Inputs

- The tray photo (JPEG/PNG).
- `expected_count` from POS (a KiotViet snapshot, a tray master or a form
  field). Optional.
- The previous **approved** scan of the same tray, if one exists.
- `attempt`: the number of re-shots already taken for this tray session.

### 4.2 Tools (OpenCV 5)

| Tool | OpenCV core | Output numbers | Evidence |
|---|---|---|---|
| `assess_quality` | Laplacian variance, HSV highlight mask, histogram, tray segmentation | blur_var, glare_ratio, brightness, contrast, tray_coverage | glare / tray mask overlay |
| `rectify_tray` | contour + `approxPolyDP` quad, `getPerspectiveTransform`, `warpPerspective` | found, quad, homography | rectified tray |
| `detect` | `cv2.dnn` ONNX (YOLOX), letterbox, `NMSBoxes` | boxes, confidences, count, density | boxes overlay |
| `tile_detect` | overlapping tiles + global `NMSBoxes` merge | count, per-tile counts | tile grid overlay |
| `zoom_recount` | ROI crop + upscale (`resize` INTER_CUBIC) + re-detect | per-region counts, resolved regions | region crops |
| `reduce_glare` | highlight mask + `inpaint` (TELEA) + CLAHE on L channel | glare before/after | de-glared image |
| `compare_previous` | AKAZE/ORB features, `findHomography` (RANSAC), `warpPerspective`, `absdiff`, morphology | inliers, changed_ratio, changed regions | diff heatmap |
| `render_evidence` | drawing primitives, `addWeighted`, `imencode` | evidence keys | annotated review sheet |

### 4.3 Terminal actions

- `auto_accept`: the count is confident and matches POS, so inventory does
  not change. Status `reviewed`, flagged `auto_accepted` in the trace.
- `request_recapture`: specific, actionable re-shoot instructions (for
  example "tilt the phone about 15° away from the ceiling light"). Status
  `needs_recapture`.
- `escalate`: a human decision is needed. Status `awaiting_approval`, with
  annotated evidence and uncertain regions.

### 4.4 Policy (deterministic controller)

Budget: **at most 5 steps and 20 s wall clock**. A *step* is one controller
decision that runs perception tools. The terminal action (including
`render_evidence`) is not a step. The trace records every tool call with its
step number. When the budget is spent and no confident terminal state has been
reached, the controller escalates with reason `budget_exhausted`.

Step 1: `assess_quality(image)`.
- `tray_coverage < COVERAGE_MIN` → `request_recapture("tray_not_in_frame")`.
- `blur_var < BLUR_MIN` → `request_recapture("blur")`.
- `glare_ratio > GLARE_SEVERE` and `attempt < MAX_RECAPTURES` →
  `request_recapture("glare")`.
- `GLARE_MILD < glare_ratio` (or a severe-glare re-shot that is still severe)
  → the next step is `reduce_glare`, and counting runs on the de-glared image.

Step 2 (or 3 after glare): `rectify_tray` then `detect` on the rectified
image (the original image when no tray quad is found).

Next: if the single shot found **no items**, run `tile_detect`, because the items may
be too small for one full-frame pass.

Next: if the detections are **dense** (`density > DENSITY_MAX`, or the median
box area is below `SMALL_BOX_FRAC` of the image), run `tile_detect`. The tiled
count replaces the single-shot count.

Next: if there are **uncertain regions** (boxes with confidence in
`[UNCERTAIN_LO, UNCERTAIN_HI)`, or tile cells where the tiled pass found
*fewer* items than the single shot. More items in a tile is the expected gain of
tiling, not uncertainty), run `zoom_recount` on up to `MAX_ZOOM_REGIONS` of them. Each
resolved region updates the count.

Reconcile with POS:
- No POS count, or count == expected, and `uncertain_after == 0` and
  `mean_conf >= ACCEPT_CONF` and quality is not degraded → `auto_accept`
  (when there is no POS count, the scan is only marked pending review;
  nothing is written to inventory).
- Count ≠ expected (mismatch): if a previous approved photo exists and the
  budget allows it, run `compare_previous` to localize what changed, then
  `escalate` with the diff regions. Otherwise `escalate` straight away.
- Anything still uncertain → `escalate`.

Thresholds live in `backend/app/agent/policy.py` (`PolicyConfig`). They are
provisional until calibrated on the real validation split. They are never
tuned on the test split.

### 4.5 Planner (optional)

`AGENT_PLANNER=bedrock` puts an LLM (Amazon Bedrock Converse tool use) in
charge of choosing the next action. It chooses from the same action set,
within the same budget, and sees only numeric observations. The controller
validates every proposed action: illegal ones are rejected, and the approval
gate is enforced in code, not by the model. On any error, timeout or invalid
output, the deterministic controller takes over for the rest of the run. The
trace records `planner=bedrock|deterministic` and every fallback.

## 5. Data and model

- At least 150 real tray photos (varied light and angles, about 30 hard
  cases), labeled in CVAT with one class, `item`. Pre-labels come from an
  open-vocabulary detector.
- Split 70/15/15 with a fixed seed. The test split is frozen by SHA-256
  manifest (`datasets/vj_items/splits/test.manifest.sha256`).
- Detector: YOLOX (Apache-2.0), trained with `training/train_yolox.py`
  (config plus seed), exported to `models/trayagent_v1.onnx`, fetched with a
  SHA-256 check (`scripts/fetch_model.sh`).
- Runtime: `cv2.dnn.readNet` on the ONNX model. No Ultralytics (AGPL) in the
  runtime.
- PRD targets: count accuracy 70–85% at MVP (PRD §1.3). Reported honestly,
  whether met or not.

## 6. AWS

- EC2 Graviton (`t4g.large` default, `c7g.large` optional) running arm64
  images from ECR.
- An S3 evidence bucket with a lifecycle policy (uploads and evidence expire
  after 30 days; noncurrent versions after 7 days).
- CloudWatch: container logs, custom metrics (`AgentSteps`, `Escalated`,
  `AgentLatencyMs`) and alarms (escalation rate, p95 latency).
- HTTPS: a CloudFront distribution in front of the instance (default
  `*.cloudfront.net` certificate).
- Optional: Bedrock (planner), Polly (video narration).

## 7. Gates (definition of done)

- [ ] G1. `cv2.__version__` starts with `"5"` (test) and is shown in `/health`.
- [ ] G2. The runtime has no Ultralytics. `scripts/license_gate.py` passes with
      an empty grandfather list for runtime manifests.
- [ ] G3. `make lint && make test` are green, with counts reported.
- [ ] G4. Every tool, controller branch, API route and migration has a test.
      That includes budget exhaustion, planner failure and "approval gate
      cannot be bypassed".
- [ ] G5. The multi-arch image (amd64 and arm64) builds, and the arm64 image
      runs on Graviton.
- [ ] G6. A public HTTPS endpoint with a demo tenant and three demo trays.
      Checked in a mobile viewport.
- [ ] G7. `reports/agentic/RESULTS.md` comes from the frozen real test set:
      count MAE, exact-count accuracy, mAP@0.5, the single-shot vs agentic
      delta, escalation, recapture and false auto-accept rates, and p50/p95
      latency on Graviton. It includes at least 5 failure cases.
- [ ] G8. The technical report (MD + PDF), architecture and workflow
      diagrams, an exported trace demo and the source archive.
- [ ] G9. The demo video renders (1080p, ≤ 5:00, no music), and there is a
      runbook for it.

## 8. Responsible use

- A human approves any count that changes inventory. `POST /scans/{id}/approve`
  is the only path from `awaiting_approval` to `reviewed`, and it requires an
  approver id.
- There is an audit trail per decision (`agent_steps` and `audit_events`).
- Faces are blurred before storage (OpenCV face detection with YuNet when its
  model is present, otherwise a Haar cascade), in both originals and evidence.
- An S3 lifecycle policy limits retention.
- Limitations are documented in the technical report.

## 9. Demo video (≤ 5:00, 1080p, English, no music)

1. 0:00–0:30: team intro (`demo/video/raw/team_intro.mp4`, or a title card).
2. 0:30–1:00: the problem and why a single-shot count fails.
3. 1:00–1:40: tray A. A clean photo leads to auto-accept, with the trace
   shown.
4. 1:40–2:40: tray B. Glare leads to a specific re-shot instruction, then the
   re-shot is accepted.
5. 2:40–3:50: tray C. A dense tray plus a POS mismatch leads to tile, zoom and
   compare with yesterday, then escalation, and a human approves.
6. 3:50–4:30: architecture (OpenCV 5 on Graviton, S3 and CloudWatch) and
   honest evaluation numbers.
7. 4:30–5:00: limitations and responsible use.
