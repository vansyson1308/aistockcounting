# Gate 0A detector candidates — license & provenance record

Verified 2026-08-23 against live upstream LICENSE files (method + URLs in the
pivot plan §S; re-verify at weight download time on the GPU runner).

| Candidate | Code license | Pretrained-weight provenance | Policy call |
|---|---|---|---|
| **D-FINE** (Peterande/D-FINE) | Apache-2.0 [FETCHED] | COCO-pretrained checkpoints (+Objects365 variants) | Code SAFE. COCO-pretrained weights = CONDITIONAL under docs/dependency-policy.md §4 (COCO annotations CC BY 4.0; image copyrights individual). **Decision: usable for Gate 0A research experiments; any production model is fine-tuned from these on own/CC-BY data with provenance recorded, and this conditionality is re-reviewed before commercial ship.** |
| **RT-DETR / RT-DETRv2** (lyuwenyu/RT-DETR) | Apache-2.0 [FETCHED] | COCO (+Objects365) checkpoints | Same as above. |
| RF-DETR-base (alternate) | Apache-2.0 code + "Apache-designated" weights [FETCHED] | Roboflow-designated | SAFE (base models only; Plus models PML 1.0 excluded). |
| YOLOX (alternate) | Apache-2.0 [FETCHED] | COCO | Same CONDITIONAL-weights note. |
| Ultralytics YOLOv8 (dataset's own baseline) | AGPL-3.0 | — | **Excluded from our experiments and product** (policy). Noted only because the SoccerTrack-v2 baseline kit uses it; our runners replace it. |

Fine-tuning data: SoccerTrack v2 (CC BY 4.0 — commercially clean, attribution
required) — TRAIN matches only per `ml/gate0a/split_manifest.yaml`.

ReID: torchreid (MIT) OSNet trained/fine-tuned on SoccerTrack v2 crops is the
intended Gate configuration; torchvision ResNet-18 ImageNet features are the
documented research-phase fallback (torchvision disclaims weight terms —
production embedders are retrained on own data per policy). Generic
pedestrian-ReID checkpoints trained on Market/Duke/MSMT are **not** used
(research-restricted data).

Dependency gate: `python scripts/license_gate.py` must pass in the experiment
environment before any run is recorded.
