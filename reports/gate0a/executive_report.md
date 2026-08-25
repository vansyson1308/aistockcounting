# Gate 0A — Execution Report (Revision 1)

**Status: `BLOCKED — REAL GPU + REAL v2-DATA GATE 0A NOT EXECUTED`**
(not PASS / not FAIL; per instructions §17 a verdict is never fabricated).
Machine-readable record: `verdict.json` (frozen-thresholds sha256 inside).

## What blocked it (verified, not assumed)

1. **No CUDA GPU**: no `nvidia-smi`, no `/dev/nvidia*`, no `nvcc`
   (`environment.json`); `list_environments` shows this account has exactly
   one execution environment — this CPU container. Detector fine-tuning and
   GPU-scale inference cannot run.
2. **Primary dataset unreachable**: SoccerTrack v2 is distributed solely via
   `huggingface.co` (verified from the dataset's own toolkit repo), and this
   environment's egress gateway denies it (CONNECT 403 policy denial, logged
   by the proxy). Alternates checked and denied: Google Drive, GitHub Pages,
   Kaggle, hf-mirror, Zenodo. The reachable GitHub toolkit repo contains no
   data files and no release assets. Nothing about the dataset blocks us —
   data is CC BY 4.0.

**Unblock = either** allow `huggingface.co` (+`cdn-lfs.huggingface.co`) in
this environment's network policy (CPU-valid v2 stages then run here), **or**
run `ml/gate0a/README.md` steps 7–15 on any machine with HF access + a CUDA
GPU. `fetch_data.md` has exact download commands.

## Real evidence produced anyway (no synthetic substitutes)

| Stage | Result |
|---|---|
| Environment/repro baseline | `environment.json` — git SHA 42ac382, thresholds sha256 0d8bb0d6…, manifests hashed |
| Dataset protocol | Official match-disjoint split adopted verbatim and frozen (`ml/gate0a/split_manifest.yaml`): TRAIN 7 / VAL 1 (118578) / TEST 2 (128057, 132831 — per-half sequences) |
| Real GT staged | SoccerTrack **v1** sample from the v1 repo: 25 s fixed wide-view full pitch, 22 players, 16,500 boxes — preparatory evidence only, never training data |
| Integrity audit | `data_integrity.md`: 0 invalid boxes, 0 duplicates, 0 frame gaps, 0 intra-track holes |
| **Evaluator sanity A/B/C (real GT)** | **ALL 11 CHECKS PASSED** (`sanity_checks.json`). A: perfect prediction → HOTA/DetA/AssA/IDF1 = 1.0, IDSW 0. B: permuted IDs → DetA 0.9995 stays, AssA 0.164, IDF1 0.306, 87 switches (scorer measures identity, not boxes). C: 30% drops → DetA 0.699 ≈ expected 0.70; IDF1 0.823 matches the closed-form 0.8235 |
| **O1 oracle (real GT, GT boxes, no IDs)** | Purity mode (default margin 0.15): HOTA 0.948 / AssA 0.901 / IDF1 0.926, 29 tracklets, 37 ambiguity terminations, integrity 0.926. **Continuity mode: perfect 1.000 HOTA, 0 switches.** Finding: on easy, oracle-box segments the untuned purity margin only fragments (−5 HOTA) — the margin is confirmed as a VAL-tuned dial whose value must be earned on dense v2 segments, exactly as the protocol prescribes. CPU tracking throughput: 923 fps at 22 objects/frame |
| O2/O3 | SKIPPED with recorded reason (require real crops → video; never simulated). Runner + real-crop embedder implemented and unit-tested |
| Dense-window procedure | Selector frozen + validated on real GT (`dense_windows_v1sample_demo.yaml`); v2 manifest generation command frozen in `ml/gate0a/dense_eval_manifest.yaml` (GT-only, runs before any predictions) |
| Detector stage | License/provenance record done (`detection/detector_licenses.md`); px-height↔recall harness built + tested; fine-tune/inference = handoff |
| Pipeline P1–P4 + stride | Runner built + unit-tested (incl. stride mechanics); execution = handoff |
| Compute | `compute/profiling.csv` — MEASURED CPU numbers only; GPU columns explicitly blocked, nothing extrapolated |
| Camsim §19 update | Provisional-threshold re-rank incl. the new **Dn** variant (`camsim_update/`): Dn delivers B/C-class pixel density (min 67–69 px) with D-class set-piece occlusion (0.0–0.5%) at 6 cameras; measured-recall re-rank pending detector stage |

## Bottleneck diagnosis (of the gate itself)

`COMPUTE-LIMITED` + `DATA-LIMITED` (environment infrastructure), jointly and
completely. Nothing observed so far is `ASSOCIATION-LIMITED`: the only real
association evidence (O1) is strong, consistent with the published
oracle-association ceiling on football.

## Standing rules honored

Thresholds untouched after results (sha256 in `verdict.json` matches the
pre-experiment record). No GT identity/team as model input. No manual track
repair. No test-set tuning (TEST data never even reached the environment).
No synthetic results presented as football-video results. Phase 0b not
started.
