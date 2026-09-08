# Gate 0A cloud layer — Stage 0 + 1 + 2 (Kaggle / HF Jobs)

```
DIAGNOSTIC — NOT OFFICIAL GATE 0A VERDICT
TEST SET UNTOUCHED
```

Thin orchestration that runs the **frozen Gate 0A runners on real
SoccerTrack-v2 footage** on an ephemeral GPU, with no owner-local compute.
The official gate (`ml/gate0a/thresholds.yaml`, `split_manifest.yaml`,
`dense_eval_manifest.yaml`) is untouched; the TEST matches (128057, 132831)
are refused at every layer (`hf_data.assert_not_forbidden`).

## What the three stages do

| Stage | Module | Output |
|---|---|---|
| 0 — inventory & scientific freeze | `stage0.py` | live HF tree + sizes, narrow download of **one** match/half (VAL `118578_1st`), GT audit, evaluator sanity A/B/C on real v2 GT, unit convention check, GSR role/team link (scoring only), **frozen GT-only windows** TUNE/OPEN/DENSE/FAR |
| 1 — real pipeline probe | `stage1.py` | one sequential decode pass: real detector (D-FINE via `transformers`, RT-DETRv2 fallback, tiled at native resolution) + real crop embeddings → **crown-jewel cache**; ambiguity-margin sweep on TUNE only; P1–P4 (+P4_noteam) on OPEN/DENSE/FAR; px-height→recall; ReID diagnostics; measured compute profile |
| 2 — oracle vs real | `stage2.py` | O1–O3 (+O4 oracle-team upper bound, labeled) from cached GT-box embeddings; gap tables; evidence-based bottleneck label; diagnostic maturity (Level 1 / 1.5 / 2); artifact manifest; executive report |

The scientific criteria live in `diagnostic_contract.yaml` (hashed into
every manifest; frozen before predictions exist). Engineering knobs live in
`config/stage012.yaml`.

## Launch on Kaggle (owner: browser only)

1. Request/confirm access to the gated dataset in a browser:
   <https://huggingface.co/datasets/atomscott/soccertrack-v2> and create a
   **read** token (<https://huggingface.co/settings/tokens>).
2. Kaggle → Add-ons → Secrets: add `HF_TOKEN` (required) and optionally
   `GH_PAT` (fine-grained, contents read/write on this repository only —
   enables automatic push of the small report tree to the run branch).
3. Kaggle → Code → New Notebook → File → Import Notebook → upload
   `notebooks/gate0a_stage012_kaggle.ipynb` (or paste the GitHub URL of that
   file on the run branch).
4. Notebook settings: **Accelerator = GPU** (T4 x2 or P100 as allocated),
   **Internet = On**, Persistence = Files (optional).
5. **Save Version → Save & Run All (Commit)**. Everything after that is
   autonomous and resumable: a re-run reuses valid caches
   (`SKIP — CACHE VALID`) and recomputes only invalidated steps.

Results: `/kaggle/working/gate0a_outputs/reports/gate0a/cloud/stage012/`
(also zipped as `gate0a_stage012_reports.zip` in the notebook Output tab).
With `GH_PAT`, the same tree is committed to the run branch in one commit —
never to `main`.

If `HF_TOKEN` is missing or access is not yet granted, the run prints
`OWNER UI ACTION REQUIRED` (exit code 3) and produces no partial evidence.

## Storage layout on the runner

```
/kaggle/working/gate0a_outputs/         (persisted, 20 GiB budget)
  reports/gate0a/cloud/stage012/        report tree (small; pushed/zipped)
  cache/<ROLE>/det.txt det_emb.npz gt_emb.npz pass.json frame_pass.cache.json
  data/                                 GT copies, team labels, frozen windows
  clips/                                optional ffmpeg exports of the windows
  state/stage{0,1,2}.json               resume state
/kaggle/tmp/gate0a_scratch/             (scratch, not persisted)
  hf/                                   dataset video + model weights caches
```

Downstream steps (MOT, reconciliation, TrackEval, O1–O4) are CPU-only and
re-runnable from `cache/` without the GPU or the source video.

## Reuse map (no duplicated science)

`runners/audit_data.audit_gt`, `runners/sanity_checks.run`,
`runners/select_dense_windows.frame_crowding`, `runners/run_oracle.*`
(`gt_to_detections`, `run_online`, `tracker_to_frames`, `tracker_to_tracklets`,
`score`), `runners/px_height_recall.bucket`, `ml.associate` (`reconcile_with_stats`
adds accounting only), `ml.associate.team_cluster.assign_teams`,
`ml.eval.*` (native metrics + official TrackEval HOTA).

## Local checks

```
PATH=$PWD/.venv-ml/bin:$PATH ./scripts/ci_ml.sh     # license gate, ruff, tests, camsim
```

`ml/tests/test_cloud_*.py` cover tree parsing, allow-pattern planning, GT
policy, window selection, tiling/NMS geometry, caching, contract/units,
manifest redaction, variants/bottleneck rules, and an offline end-to-end
smoke on a synthetic video with a fake detector — **software mechanics
only, never product evidence**.
