# Dependency & Data Licensing Policy

Status: active from Phase 0a of the football-tracking pivot (plan §S).
Enforced in CI by `scripts/license_gate.py` over every dependency manifest.

## Rules

1. **Allowed in product code and product images:** permissive licenses only —
   MIT, BSD, Apache-2.0, ISC, PSF, Zlib, MPL-2.0 (file-level copyleft
   acceptable with care).
2. **Banned from product code and product images:** AGPL, GPL (any version),
   LGPL static linking without review, SSPL, Hippocratic License (HL3),
   non-commercial licenses, and components with **no license file**
   (all rights reserved). These may be read as *papers/reference only*;
   algorithms may be clean-room reimplemented from publications
   (copyright covers code, not ideas — patent review is tracked separately).
3. **Conditional (case-by-case, recorded here when adopted):**
   - FFmpeg: pure-LGPL build only (no `--enable-gpl`, so no x264/x265),
     dynamically linked, license text shipped, source offer documented in the
     release checklist.
   - NVIDIA TensorRT / DeepStream: proprietary free SLAs permitting
     redistribution of runtimes; re-review the SLA at each version bump.
4. **Model weights:** a weight file inherits the terms of its training data
   and of the code that produced it. Weights trained on non-commercial
   datasets (SoccerNet, SportsMOT, MOT17/20, CrowdHuman, ImageNet-terms data)
   must never ship in the product. Preferred pretrained backbones with clean
   provenance: DINOv2 (Apache-2.0 release), RF-DETR "Apache-designated"
   weights, PP-OCR models. Every registered production model records its
   dataset provenance.
5. **Datasets:** non-commercial datasets never touch production training
   infrastructure. They are allowed for research-phase experimentation and
   benchmarking only (Gate 0A), and are retired as eval sources once
   own-footage benchmarks exist. SoccerTrack v2 (data CC BY 4.0) is the
   standing exception: commercially usable with attribution.

## Recorded decisions

| Date | Decision |
|---|---|
| 2026-08-23 | **Ultralytics (AGPL-3.0): REPLACE, not license.** The product
detector stack is Apache-2.0 (D-FINE / RT-DETR / RF-DETR-base / YOLOX
candidates, chosen by Gate 0A benchmark). Rationale: removes AGPL §13
network-copyleft exposure and vendor coupling; the Apache detector field is
competitive (plan §E/§S). The Ultralytics Enterprise license remains a
documented fallback if benchmarks ever justify it. |
| 2026-08-23 | **Legacy exception (expires at Phase 0b):** the pre-pivot
inventory app pins `ultralytics` in `backend/requirements.txt` and
`training/requirements-train.txt`. These manifests are grandfathered in the
license gate until the Phase 0b migration deletes the legacy inference path.
New code must not import ultralytics; the gate bans it everywhere else. |

## Adding a dependency

1. Verify the license against the upstream LICENSE file (not a package index
   summary); record it in `THIRD_PARTY_NOTICES.md`.
2. If it is not plainly permissive, add a Recorded decision row here.
3. CI (`scripts/license_gate.py`) fails on banned names in any manifest that
   is not explicitly grandfathered; do not extend the grandfather list —
   it only shrinks.
