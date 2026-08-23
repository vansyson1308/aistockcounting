# Third-Party Notices

This project is proprietary (see `LICENSE`). It depends on third-party
open-source components under their own licenses. This file lists the
runtime-relevant components and their verified licenses. The authoritative
policy for what may be added is `docs/dependency-policy.md`, enforced by
`scripts/license_gate.py` in CI.

Licenses below were verified against upstream LICENSE files on 2026-08-23
(see the pivot plan, section S, for verification details).

## New ML / tooling components (Phase 0a onward)

| Component | License | Use |
|---|---|---|
| numpy | BSD-3-Clause | numerics |
| scipy | BSD-3-Clause | assignment (Hungarian), filtering |
| matplotlib | PSF-based (BSD-compatible) | camsim heatmap rendering (dev tool) |
| pyyaml | MIT | configs |
| pytest | MIT | tests (dev only) |
| ruff | MIT | lint (dev only) |
| TrackEval (JonathonLuiten/TrackEval) | MIT | tracking metrics (HOTA/CLEAR/Identity) |
| Pillow | MIT-CMU/HPND | image IO (dev/eval tooling) |

Planned (Gate 0A execution on a GPU machine; not vendored here yet):
D-FINE (Apache-2.0), RT-DETR (Apache-2.0), YOLOX (Apache-2.0),
torchreid (MIT), PyTorch (BSD-style), torchvision (BSD-3-Clause),
OpenCV (Apache-2.0), SAHI (MIT), supervision (MIT),
roboflow/trackers (Apache-2.0). Each must pass the dependency policy
before being added to any manifest.

## Datasets (not redistributed in this repository)

| Dataset | Terms | Permitted use here |
|---|---|---|
| SoccerTrack v2 | code MIT; data CC BY 4.0 | Gate 0A evaluation and (with attribution) training |
| SoccerNet (all tracks) | NDA, research/education non-commercial | research-phase benchmarking only; never in production training |
| SportsMOT | CC BY-NC 4.0 | research-phase only; never in production training |
| MOT17/MOT20, CrowdHuman, ImageNet | non-commercial terms | research-phase only; never in production training |
| COCO | annotations CC BY 4.0; images individually licensed | pretrained-backbone provenance noted per model |

## Legacy application components (pre-pivot; scheduled for Phase 0b review)

The existing inventory application (`backend/`, `frontend/`, `training/`)
predates this policy. Its dependencies include `ultralytics` (AGPL-3.0),
which is **banned for the product core** and is carried only as a
grandfathered legacy exception until the Phase 0b migration removes it
(see `docs/dependency-policy.md`). No new code may import it.
