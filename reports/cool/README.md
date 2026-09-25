# COOL benchmark (Best Use of COOL): not run yet

**Status:** blocked on the owner's approval (BLOCKERS B-005). No COOL or Graviton numbers are
claimed anywhere in this repository.

- **COOL:** Cloud-Optimized OpenCV Library, an OpenCV 5 build with Arm KleidiCV
  optimisations, sold on AWS Marketplace as "Cloud Optimized OpenCV For AWS Graviton4"
  (listing `prodview-fdvbfiewzuehs`).
- **Terms (as seen on 2026-09-25):** a 7-day free trial, then usage-based paid pricing,
  and the trial converts to a paid subscription unless it is cancelled. Graviton4 means
  c8g/m8g/r8g instances. Check the current listing before subscribing.

## Protocol (ready to run)
The same script and inputs run on every machine; each run appends one line to `runs.jsonl`:
```bash
# 1. x86 baseline (c7i.large, stock opencv-python-headless 5.0.0.93)
python benchmarks/cv_bench.py --label c7i.large-stock --out reports/cool/runs.jsonl
# 2. Graviton, stock wheel (c7g.large or the c8g.large used for COOL)
python benchmarks/cv_bench.py --label c8g.large-stock --out reports/cool/runs.jsonl
# 3. Graviton + COOL (on the Marketplace AMI/container, with its cv2 on PYTHONPATH)
python benchmarks/cv_bench.py --label c8g.large-COOL --out reports/cool/runs.jsonl
# 4. Render the table
python benchmarks/cv_bench.py --report reports/cool/runs.jsonl   # → reports/cool/RESULTS.md
```
Each run records the OpenCV build flags (including whether KleidiCV is present), the thread
count and the CPU features. Record the COOL version and the instance configuration in
`RESULTS.md` by hand as well.

Workloads:
- the primitives COOL targets: resize INTER_AREA, adaptiveThreshold Gaussian, findContours,
  GaussianBlur, cvtColor, warpPerspective;
- TrayAgent's own `assess_quality`, `rectify_tray` and `tile_detect`, on phone-resolution
  (4032×3024) inputs.
