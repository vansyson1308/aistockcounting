# TrayAgent: competition status

Last updated: 2026-09-25 (end of the first build session)
Branch: `claude/relaxed-wozniak-nhlyvm` (acts as `opencv-comp`; see DECISIONS D-002).
Draft PR: vansyson1308/aistockcounting#5.
Deadline: 2026-10-26 23:59 PT · Code freeze target: 2026-10-22.

> **The submission is NOT ready yet.** The software, infrastructure-as-code, evaluation
> harness, report and video pipeline are built and tested. The results, the deployment
> and the final video depend on the owner's inputs: real photos (B-001) and AWS
> credentials (B-002).

## Checklist

- [x] Phase 0: setup and recon
- [x] Phase 1: OpenCV 5 migration
- [~] Phase 2: data and model. **Tooling done and verified**; labelling and training wait on photos (B-001)
- [x] Phase 3: OpenCV 5 tool library
- [x] Phase 4: agent (controller, planner, trace, routes, approval gate)
- [x] Phase 5: frontend (live timeline, re-shot flow, review page). Checked in an iPhone 13 viewport against the local stack
- [~] Phase 6: AWS. **CDK, scripts and tests done** (synth OK without credentials); deployment waits on credentials (B-002)
- [~] Phase 7: evaluation. **Harness done** (frozen-set guard, failure gallery); results wait on photos (B-001)
- [ ] Phase 8: COOL. Harness and protocol ready; waiting on the owner's approval of the paid Marketplace subscription (B-005)
- [~] Phase 9: submission materials. Report MD+PDF, diagrams, trace demo (synthetic-labelled), README, Devpost fields and `make source-archive` are done; they need real numbers and the endpoint URL
- [~] Phase 10: video pipeline. Done and rendered once (a synthetic rehearsal, 165.2 s, 1920×1080, checked with ffprobe); the real render needs photos, the endpoint and the team intro

## SPEC §3 MVP

| Item | State | Evidence |
|---|---|---|
| M1 photo → count via OpenCV 5 DNN | done (code) | `backend/app/services/detector_cv.py`; `tests/test_detector_cv.py` (cv2.dnn round trip under AUTO/NEW/CLASSIC); YOLOX export verified to load in `cv2.dnn` (synthetic mechanics check) |
| M2 tool library | done | `backend/app/agent/tools/*`; `tests/test_agent_tools.py` |
| M3 bounded agent | done | `controller.py`, `policy.py`; `tests/test_agent_policy.py`, `tests/test_agent_controller.py` |
| M4 approval gate | done | `api/routes/agent.py`; `tests/test_agent_api.py::test_approval_gate_cannot_be_bypassed` |
| M5 trace + audit | done | `agent_steps` (migration 0004), `trace.py`; API tests |
| M6 mobile UI | done | `frontend/src/app/scan`, `review/[id]`; vitest page tests; mobile-viewport run |
| M7 AWS Graviton, S3, CloudWatch | code done, **not deployed** | `infra/aws/` (31 tests, synth); B-002 |
| M8 honest evaluation | harness done, **no results** | `training/scripts/agent_eval.py`; B-001 |

## SPEC §7 gates

| Gate | State | Evidence |
|---|---|---|
| G1 OpenCV 5.x test + `/health` | ✅ | `tests/test_opencv5.py`; `/health` → `"opencv":"5.0.0"` (local stack, and the arm64 image under QEMU) |
| G2 no Ultralytics; license gate | ✅ | `scripts/license_gate.py`: OK, the grandfather list is empty and runtime manifests can never be grandfathered |
| G3 lint + tests green | ✅ | `make lint` green; `make test`: backend **192 passed, 1 skipped** (the online Postgres test runs with `TEST_DATABASE_URL`, and passed manually), frontend **48 passed**; infra **31 passed**; CI green on 10d8493 and 416199c |
| G4 tests for tools, branches, routes, migration | ✅ | including budget exhaustion (steps and time), planner failure and illegal proposals, and the approval gate |
| G5 multi-arch image, arm64 runs | ✅ locally / ⏳ Graviton | buildx amd64+arm64 built; arm64 `/health` under QEMU; CI docker-build job (multi-arch) green |
| G6 public HTTPS endpoint, 3 demo trays | ⏳ | B-002 (credentials) and B-001 (demo photos) |
| G7 RESULTS.md from the frozen real test set | ⏳ | B-001 |
| G8 report PDF, diagrams, trace demo, source archive | ✅ (numbers pending) | `docs/competition/TECHNICAL_REPORT.{md,pdf}`, `architecture.png`, `agent_workflow.png`, `trace_demo/`, `make source-archive` |
| G9 video renders + runbook | ✅ pipeline / ⏳ real render | `demo/video/`, `docs/competition/VIDEO_RUNBOOK.md` |

## Owner actions (in order)

1. **Photos** (B-001): at least 150 real tray photos in `datasets/vj_items/raw/` (about 30 hard ones in `raw/hard/`), 3 pairs in `raw/pairs/`, and the demo trays in `raw/demo/`: `A_clean`, `B_glare`, `B_reshot`, `C_dense`, `C_prev`, with the POS counts.
2. **AWS** (B-002): credentials for `ap-southeast-1` (or another region). Approve the running cost: t4g.large is roughly $50/month on-demand (check the current price).
3. **Labels:** review the pre-labels in CVAT (`docs/competition/LABELING_HOWTO.md`, about 30 s per image).
4. **Decisions:** COOL subscription yes/no (B-005); removing the football directories yes/no (B-004); repo access or source archive for the judges; mark the GitGuardian findings as false positives (B-006).
5. **After those:** the engineer trains, evaluates, deploys and records. The owner then records the team intro (`demo/video/raw/team_intro.mp4`), re-renders (`demo/video/build.sh`), uploads the video, pastes `DEVPOST_SUBMISSION.md` and submits.

## Engineer next steps once photos and AWS arrive

`make data-ingest` → `make data-prelabel` → CVAT review → `cvat_tasks.py export-yolo` + `unpack-export`
→ `make data-split` → `make train-yolox` (GPU or CPU) → commit `models/trayagent_v1.{json,sha256}`
→ calibrate the `PolicyConfig` thresholds on **val** → `scripts/aws/deploy.sh` with `MODEL_PATH`
→ `make eval-agent MACHINE=t4g.large` **on the Graviton host** → `scripts/export_trace_demo.py api …`
→ update the report's section 6 from RESULTS.md → `RECORD=1 BASE_URL=… demo/video/build.sh`.

## Unverified / not measured

- **No accuracy, no Graviton latency, no COOL numbers exist.** Every number in the repository
  so far comes from tests or engineering checks on synthetic fixtures, and is labelled as such.
- The CDK stack, `deploy.sh`, `teardown.sh`, CloudFront and the CloudWatch alarms have never run
  against AWS.
- The Bedrock planner has only been tested against a fake client. The model id must be set by the owner.
- The Polly narration was not produced; the rehearsal used espeak-ng.
- OWLv2 pre-labelling was not run: Hugging Face is blocked in the dev sandbox.
- Engineering note: in the x86 dev container, the COCO YOLOX-nano 416 forward took about 12 ms with
  `ENGINE_NEW` vs about 26 ms with `ENGINE_CLASSIC`. This is not a result.

## Blockers
See `BLOCKERS.md` (B-001 to B-006).
