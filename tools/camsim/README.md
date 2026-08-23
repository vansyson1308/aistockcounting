# camsim — camera-geometry simulation (plan §F.6)

Parametric model of sensor + lens + mount pose over a football pitch,
producing per-configuration fields: **px/m**, **expected player bbox height
(px)**, **elevation angle**, and an **occlusion-severity proxy** from
formation-realistic sampled placements. Architecture selection (plan
§F A/B/C/D) is made from these numbers plus Gate 0B field validation.

Run (repo root, needs `ml/requirements.txt` deps; matplotlib optional for
heatmap PNGs):

```bash
python -m tools.camsim.run --all --heights 8 12 15 20 25 --out outputs/camsim
python -m tools.camsim.run --preset B --heights 15 --plots --out outputs/camsim
```

## First sweep (2026-08-23, preset defaults: 24 m stand setback, 4K sensors)

Player bbox height = vertical px/m × 1.8 m, per-cell best camera; coverage
fractions vs working thresholds detect ≥20 px / ReID ≥40 px / OCR ≥110 px
(Gate 0A replaces the detect floor with a measured px-height↔recall curve).

| Rig | @15 m: bboxH min/p10/med (px) | detect / ReID / OCR coverage | occl. open/set-piece |
|---|---|---|---|
| A — 1×130° wide | 18 / 19 / 27 | 83% / 17% / 0% | 0.3% / 3.3% |
| B — 2×68° halves | 49 / 58 / 78 | 100% / 100% / 16% | 0.3% / 2.1% |
| C — 4×45° quarters | 82 / 94 / 125 | 100% / 100% / 68% | 0.2% / 2.7% |
| D — 4 distributed (wide lenses) | 32 / 36 / 48 | 100% / 76% / 0% | 0.2% / **0.4%** |

Height sweep (B): min elevation 4.3°→13.3° and set-piece occlusion
4.2%→1.3% from 8 m→25 m — height is the occlusion lever the plan claims.

Early readings (hypotheses for Gate 0B, not decisions):
1. **A is quantitatively demo-only** — detection-marginal pixels over most
   of the pitch, no ReID margin, no OCR anywhere.
2. **B clears detection+ReID thresholds pitch-wide** at every height tried;
   its OCR zone is the near strip only (~16–21%) — consistent with the
   plan's "read numbers opportunistically, propagate via tracks".
3. **C's upside is identity**: ~70% of the pitch OCR-capable for 2× B's
   GPU/hardware.
4. **D's upside is occlusion-breaking, not pixels** (with wide lenses):
   any-camera-resolves counts; set-piece occlusion ~5–10× better than
   single-viewpoint rigs. A D-with-narrow-lenses variant would dominate
   everything at ~4× cost — sweep before Gate 0B.
5. **Modeling result that reshaped the presets**: at small stand setbacks a
   single 16:9 camera cannot fit near touchline + far touchline in its
   vertical FOV; presets now use a 24 m setback and aim at the
   vertical-bisector ground point.

## Caveats (by design, until Gate 0B)

- The occlusion proxy uses synthetic 4-4-2-ish placements + a set-piece
  clustering mode; plug real trajectories (SoccerTrack v2) into
  `occlusion.sample_positions` for production ranking. Rates are a relative
  ranking signal (IoU ≥ 0.3 overlap of nearer players), not absolute truth.
- Distortion is Brown-Conrady polynomial — adequate for moderate lenses,
  optimistic for true fisheyes (arch. A).
- Every threshold here is provisional until Gate 0A measures the
  px-height↔recall curve and Gate 0B validates predictions against real
  footage (±15% tolerance per plan §X.5).
