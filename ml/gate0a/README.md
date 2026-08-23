# Gate 0A — Algorithmic Feasibility: runbook & execution state

**Hypothesis under test:** a license-clean detector + purity-first online
MOT + sports ReID + fully automatic offline tracklet reconciliation can
maintain football-player identity on real fixed-view footage, without any
human track correction, at quality clearing the FROZEN thresholds in
`thresholds.yaml` (sha256 recorded in `reports/gate0a/environment.json`;
never modified after seeing results).

**Execution state (2026-08-23):** all CPU-and-data-reachable stages are
DONE with real data; the remaining stages are **BLOCKED in the authoring
environment** (no GPU; the primary dataset's only host, huggingface.co, is
denied by the environment's network egress policy — full evidence in
`reports/gate0a/executive_report.md`). Everything below runs unchanged on a
machine with (a) huggingface.co access and (b) a CUDA GPU.

## Frozen experimental contract

- Thresholds: `thresholds.yaml` (immutable; §X.4 of the plan).
- Split: `split_manifest.yaml` — official SoccerTrack-v2 protocol, match-
  disjoint (TRAIN 7 / VAL 118578 / TEST 128057+132831 per half). TEST never
  influences development.
- Dense windows: `dense_eval_manifest.yaml` — selector + params frozen;
  windows generated from v2 TEST GT as the FIRST post-download step, before
  any predictions exist.
- Purity policy: fragment on ambiguity, never guess; `ambiguity_margin` is
  VAL-tunable only (real O1 evidence on why: see oracle results).

## Runbook (execute in this order)

Steps 1–6 are DONE here (real data where available); 7+ are the handoff.

1. Environment record → `reports/gate0a/environment.json`. ✅ DONE
2. Data: `fetch_data.md` (exact commands). ✅ v1 sample staged;
   ❌ v2 BLOCKED (network).
3. Integrity audit: `runners/audit_data.py` → `reports/gate0a/
   data_integrity.md`. ✅ run on real v1 sample; rerun on the v2 snapshot.
4. Evaluator sanity A/B/C: `runners/sanity_checks.py --gt <gt.txt>`.
   ✅ ALL 11 CHECKS PASSED on real GT (`reports/gate0a/sanity_checks.json`).
   Non-zero exit = STOP and debug the evaluator.
5. Dense windows (v2, at data arrival, BEFORE any predictions): run the
   frozen command in `dense_eval_manifest.yaml`. ✅ selector validated on
   real GT (`reports/gate0a/dense_windows_v1sample_demo.yaml`).
6. Oracle ladder O1: `runners/run_oracle.py --stages o1`. ✅ run on real GT
   (`reports/gate0a/oracle/`). On v2: run per TEST sequence + full halves.
7. Oracle O2/O3 (needs video + torch): install
   `torch torchvision opencv-python-headless` (CPU ok for oracle scale),
   then `runners/run_oracle.py --stages o1 o2 o3 --video <panorama.mp4>`.
   O4 (oracle team labels) only as an explicitly-labeled diagnostic.
8. Detectors (GPU): fine-tune **D-FINE** and **RT-DETRv2** (licenses:
   `reports/gate0a/detection/detector_licenses.md`) on TRAIN matches via
   each repo's native tooling; VAL for all tuning/selection/early-stop.
   Export detections per sequence in the MOT det interchange format
   (`frame,-1,x,y,w,h,score,-1,-1,-1`) at operating + low thresholds.
9. px-height↔recall per detector: `runners/px_height_recall.py` →
   `reports/gate0a/detection/px_height_recall.csv`; feed measured bins back
   into `tools/camsim` and re-rank (step 14).
10. Freeze configurations on VAL. Then, TEST only:
    `runners/run_pipeline.py --stages p1 p2 p3 p4 --strides 1 2 3` per
    frozen TEST sequence → `reports/gate0a/tracking/`.
11. Full-half long-horizon: same runner on a full TEST half (long-horizon
    stats are in every score dict); plus player timelines.
12. Dense-window regression: evaluate final predictions inside the frozen
    windows; classify every identity failure (detector miss / ReID
    ambiguity / motion error / team misclass / merge failure / evidence
    genuinely insufficient). Human examination = evaluation only; never
    correct predictions.
13. Compute profile per stage (MEASURED only) →
    `reports/gate0a/compute/profiling.csv`.
14. Camsim update with measured curve → `reports/gate0a/camsim_update/`.
    ✅ provisional-threshold sweep incl. the Dn variant done; re-run with
    measured bins.
15. Verdict: assemble final TEST metrics JSON → `runners/make_verdict.py
    --metrics ... --evidence ...` → `reports/gate0a/verdict.json`. The
    decision function + thresholds are frozen; never hand-write a verdict.
    ✅ current verdict.json = BLOCKED (real v2 execution not possible here).

## Interchange formats

- GT and predictions: MOTChallenge (`ml.eval.mot_io`).
- Detections: MOT det rows with id −1 (`frame,-1,x,y,w,h,score,-1,-1,-1`).
- Embedding stage consumes the sequence video directly (real crops only —
  synthetic embeddings are banned for gate evidence).

## Discipline reminders

No GT identity or GT team labels as model input in production-like runs
(GT team only for scoring; O4 oracle-team is a labeled diagnostic). No
manual track repair anywhere. No tuning on TEST. A test-exposed bug is
fixed + regression-tested + rerun as a new documented revision.
