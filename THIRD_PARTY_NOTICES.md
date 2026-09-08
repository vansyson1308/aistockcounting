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

### Gate 0A cloud diagnostic runtime (`ml/gate0a/cloud/requirements-cloud.txt`)

| Component | License | Use |
|---|---|---|
| PyTorch | BSD-style | inference runtime (taken from the cloud image; not pinned) |
| torchvision | BSD-3-Clause | ResNet ImageNet backbone for diagnostic embeddings |
| transformers (Hugging Face) | Apache-2.0 | D-FINE / RT-DETRv2 inference (`AutoModelForObjectDetection`) |
| huggingface_hub | Apache-2.0 | gated dataset access, selective `snapshot_download` |
| opencv-python-headless | Apache-2.0 | video decode, crops |

Pretrained weights used by the cloud diagnostic — **RESEARCH-DIAGNOSTIC
class only, never shipped**: `ustc-community/dfine-large-coco` and
`PekingU/rtdetr_v2_r50vd` (Apache-2.0 code; COCO-2017-trained weights with
ImageNet-pretrained backbones) and torchvision `ResNet50 IMAGENET1K_V2`
(ImageNet-derived). Product models are retrained on own data per policy
rule 4.

Planned for later phases (not vendored yet): YOLOX (Apache-2.0),
torchreid (MIT), SAHI (MIT), supervision (MIT), roboflow/trackers
(Apache-2.0). Each must pass the dependency policy before being added to
any manifest.

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
