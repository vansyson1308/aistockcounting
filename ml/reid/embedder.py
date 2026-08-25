"""Real-crop appearance embedding extraction.

`embed_sequence(video, gt_frames)` decodes the sequence video, crops every
GT/detection box, and embeds crops with a backbone. Returns
{(frame, det_index): unit-norm vector}.

Backbones (license-reviewed, see docs/dependency-policy.md):
- "torchvision-resnet18": ImageNet-pretrained torchvision weights —
  acceptable for research-phase Gate experiments; production models are
  retrained on own data per policy (torchvision disclaims weight terms).
- "osnet": torchreid (MIT) OSNet fine-tuned on football crops — the intended
  Gate 0A configuration on the GPU runner (see ml/gate0a/README.md).
- any callable `(N,H,W,3 uint8) -> (N,D) float` for tests.

torch/cv2 are imported lazily; environments without them get a clear error
instead of an import-time failure.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np

CROP_SIZE = (128, 64)  # h, w — standard ReID aspect


class EmbedderUnavailable(RuntimeError):
    pass


def _load_torchvision_backbone(device: str):
    try:
        import torch
        import torchvision
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise EmbedderUnavailable(
            "torch/torchvision not installed — install per ml/gate0a/README.md"
        ) from exc

    weights = torchvision.models.ResNet18_Weights.IMAGENET1K_V1
    model = torchvision.models.resnet18(weights=weights)
    model.fc = torch.nn.Identity()
    model.eval().to(device)
    mean = torch.tensor([0.485, 0.456, 0.406], device=device).view(1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225], device=device).view(1, 3, 1, 1)

    @torch.no_grad()
    def forward(batch_u8: np.ndarray) -> np.ndarray:
        x = torch.from_numpy(batch_u8).to(device).permute(0, 3, 1, 2).float() / 255
        x = (x - mean) / std
        feats = model(x)
        return feats.cpu().numpy()

    return forward


def _crop(frame_img: np.ndarray, xyxy: np.ndarray) -> np.ndarray | None:
    h, w = frame_img.shape[:2]
    x1, y1, x2, y2 = (round(float(v)) for v in xyxy)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return None
    import cv2

    crop = frame_img[y1:y2, x1:x2]
    return cv2.resize(crop, (CROP_SIZE[1], CROP_SIZE[0]))


def embed_sequence(
    video: Path,
    gt_frames: dict,
    backbone: str | Callable = "torchvision-resnet18",
    device: str = "cpu",
    batch_size: int = 64,
    frame_offset: int = 1,
) -> dict[tuple[int, int], np.ndarray]:
    """Embed every box of every frame present in `gt_frames` from `video`.

    frame_offset maps MOT 1-based frame numbers to 0-based video frames.
    """
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover
        raise EmbedderUnavailable("opencv-python not installed") from exc

    forward = (
        backbone if callable(backbone) else _load_torchvision_backbone(device)
    )

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise EmbedderUnavailable(f"cannot open video {video}")

    wanted = sorted(gt_frames)
    out: dict[tuple[int, int], np.ndarray] = {}
    pending_keys: list[tuple[int, int]] = []
    pending_crops: list[np.ndarray] = []

    def flush():
        if not pending_crops:
            return
        feats = forward(np.stack(pending_crops))
        norms = np.linalg.norm(feats, axis=1, keepdims=True)
        feats = feats / np.maximum(norms, 1e-9)
        for key, vec in zip(pending_keys, feats, strict=True):
            out[key] = vec.astype(np.float32)
        pending_keys.clear()
        pending_crops.clear()

    video_idx = -1
    for f in wanted:
        target = f - frame_offset
        while video_idx < target:
            ok, img = cap.read()
            if not ok:
                cap.release()
                flush()
                return out
            video_idx += 1
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        for i, (_tid, xyxy, _c) in enumerate(gt_frames[f]):
            crop = _crop(img_rgb, xyxy)
            if crop is None:
                continue
            pending_keys.append((f, i))
            pending_crops.append(crop)
            if len(pending_crops) >= batch_size:
                flush()
    cap.release()
    flush()
    return out
