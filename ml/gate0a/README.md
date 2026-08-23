# Gate 0A — Algorithmic Feasibility Experiment (plan §X.2–X.4)

**Hypothesis under test:** a license-clean detector + purity-first online
tracker + automatic offline tracklet reconciliation holds football player
identities on fixed-view footage — no human track-fixing — at association
quality sufficient to justify building the full-match platform.

This directory holds the runbook and the machine-readable decision
thresholds (`thresholds.yaml`, consumed by `ml.eval.gate`). The experiment
itself runs on a GPU machine; this repository provides the frozen harness.

## What is measured (primary gate = FINAL association quality)

- AssA, HOTA, DetA, IDF1 (TrackEval), ID switches, completeness,
  identity integrity (`ml.eval`), on SoccerTrack-v2 eval segments.
- Long-horizon identity integrity on one full half.
- Team clustering accuracy vs GSR team labels.
- Dense-occlusion audit: 3 corner-kick sequences, counting
  evidence-unresolvable identity errors (evaluation labor, TRAINING/QA ONLY).
- Ablations (reported, never gated): offline-vs-online delta;
  detection-stride ablation (25 vs 12.5 Hz with tracker bridging).
- Compute table: detector FPS per tile plan, tiles per 4K frame, VRAM,
  per-crop ReID cost, GPU-hours per processed video-hour.

## Runbook (GPU machine)

1. Environment: Python 3.11+, CUDA GPU.
   `pip install -r ml/requirements-dev.txt` plus the detector framework
   under evaluation (Apache-2.0 candidates only: D-FINE, RT-DETR;
   alternates RF-DETR-base, YOLOX). The license gate policy applies:
   no AGPL/GPL/HL3 packages (`python scripts/license_gate.py`).
2. Data (research-phase terms per docs/dependency-policy.md):
   - **SoccerTrack v2** (primary; data CC BY 4.0): follow
     https://github.com/AtomScott/SoccerTrack-v2 — 2–3 matches:
     5-minute eval segments + one full half.
   - SoccerNet-tracking clips (context check; NDA/research-only).
   Convert ground truth to MOT format (frame,id,x,y,w,h,conf,-1,-1,-1).
3. Fine-tune both detector candidates; export per-frame detections with
   embeddings (OSNet-class, torchreid) for the eval segments.
4. Online pass: `ml.track.PurityFirstTracker` over the detections →
   `to_mot_rows()` → `online.txt`.
5. Offline pass: build `ml.associate.Tracklet`s from the tracker output,
   run `ml.associate.reconcile`, re-emit rows with canonical ids →
   `final.txt`.
6. Evaluate:
   `python -m ml.eval.run_eval GT.txt final.txt --online-pred online.txt
   --hota --json results.json`
7. Verdict: fill a `GateInputs` from the results (+ team accuracy, audit
   outcome, well-detected-subset AssA) and call
   `ml.eval.gate.decide(inputs, load_thresholds("ml/gate0a/thresholds.yaml"))`.
   The verdict and reasons go into the Gate 0A report and the §A update.

## Outputs required by the plan

Benchmark report (all numbers + failure-case gallery + compute table +
stride ablation), the frozen eval harness in CI, and the go/no-go memo.
Passing 0A unlocks Phase 0b (platform migration). It does **not** validate
the camera design — that is Gate 0B (`tools/camsim` + matched-geometry
footage).
