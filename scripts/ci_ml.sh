#!/usr/bin/env bash
# CI parity for the ML core + camsim + licensing gate (run from repo root).
set -euo pipefail

python scripts/license_gate.py
ruff check ml tools/camsim scripts/license_gate.py conftest.py
pytest ml/tests tools/camsim/tests -q
# Smoke: the camera-geometry simulation must run end-to-end.
python -m tools.camsim.run --preset B --heights 15 --grid-step 6 \
  --occlusion-samples 4 --out "${CAMSIM_OUT:-/tmp/camsim-ci}"
