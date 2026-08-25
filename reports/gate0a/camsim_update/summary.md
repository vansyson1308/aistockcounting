# Camera-hypothesis ranking update (Gate 0A §19)

Sweep: architectures A/B/C/D + **Dn (new §19 variant: 2×68° pairs on BOTH
sideline masts + 2 end cameras = 6×4K, multi-viewpoint)** × heights
{12, 15, 20 m}; full table in `ranked_configs.csv`, raw fields in
`summary.json`.

## Status of the evidence

- **Thresholds are still provisional** (detect ≥20 px / ReID ≥40 px /
  OCR ≥110 px player height). The *measured* px-height↔recall curve —
  the input §19 requires — comes from the detector stage, which is
  network/GPU-blocked in this environment (see executive report). The
  harness that produces it (`ml/gate0a/runners/px_height_recall.py`) is
  built, tested, and wired into the runbook; this ranking must be re-run
  with measured bins before Gate 0B commits to hardware.
- Occlusion is the synthetic-formation proxy (relative signal only); the
  runbook's next iteration plugs real SoccerTrack-v2 trajectories into
  `tools/camsim/occlusion.sample_positions`.
- The composite score (50% p10 pixel density, 35% set-piece occlusion,
  15% OCR coverage) is a documented choice for readability, not a decision
  rule — Gate 0B decides on the underlying columns.

## What the sweep shows (provisional thresholds)

1. **Dn is the standout finding**: 67–69 px minimum player height
   (B/C-class density everywhere) **and** 0.0–0.5% set-piece occlusion
   (D-class multi-viewpoint clump-breaking) **and** OCR zones on both
   sidelines (21–37%) — at 6 cameras / ~6× GPU. It removes the
   single-viewpoint occlusion weakness that is Gate 0A's core risk.
2. **C (4×45°, one mast)** leads the single-mast field: 80+ px minimum,
   64–69% OCR coverage, 4 cameras — but keeps single-viewpoint set-piece
   occlusion (1.7–2.9%).
3. **B (2×68°)** remains the cheapest plan clearing detect+ReID pitch-wide
   (min 49 px), with the thinnest margins: OCR near-strip only, worst
   set-piece occlusion of the multi-camera rigs at low mounts.
4. **D with wide lenses** buys occlusion-breaking but sacrifices ReID pixel
   density (p10 34–36 px) — narrow lenses (Dn) are the correct way to spend
   distributed viewpoints.
5. Height: minimum elevation and set-piece occlusion improve monotonically
   with height for every rig (e.g. Dn set-piece 0.5%→0.0% from 12→20 m).

## Recommended Gate 0B slate (hypotheses to field-test, in order)

| Priority | Config | Why |
|---|---|---|
| 1 | **B @ ≥15 m** (2×68°) | cheapest viable; tests the minimum-hardware thesis; its measured far-zone recall calibrates everything else |
| 2 | **C @ 15–20 m** (4×45°) | same mast/footage session as B (add heads); resolves whether OCR-zone width justifies 2× GPU |
| 3 | **Dn** (staged: near-mast pair + far-mast pair) | only if 0A/0B show single-viewpoint association is the binding constraint — it is the engineered answer to dense-scene identity |

A/B/C/Dn share the near-mast geometry, so one Gate 0B recording session at
the simulated mount covers priorities 1–2 and half of 3.
