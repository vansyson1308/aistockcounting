"""Real appearance embeddings from actual player crops.

Primary: torchvision ResNet (ImageNet weights; BSD-3 code) — classified
RESEARCH-DIAGNOSTIC because the weights are ImageNet-derived (the product
retrains on own crops per docs/dependency-policy.md). Optional secondary:
torchreid OSNet (MIT code, ImageNet weights) when enabled and installable.

No synthetic vectors exist anywhere in this module.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np


def crop_box(img_rgb: np.ndarray, xyxy, hw: tuple[int, int]) -> np.ndarray | None:
    h, w = img_rgb.shape[:2]
    x1, y1, x2, y2 = (round(float(v)) for v in xyxy)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return None
    import cv2

    return cv2.resize(img_rgb[y1:y2, x1:x2], (hw[1], hw[0]))


@dataclass
class EmbedProfile:
    crops: int = 0
    seconds: float = 0.0
    extra: dict = field(default_factory=dict)

    def finish(self) -> dict:
        return {"crops": self.crops, "seconds": round(self.seconds, 2),
                "crops_per_second": round(self.crops / self.seconds, 1) if self.seconds else 0.0,
                **self.extra}


class TorchvisionEmbedder:
    def __init__(self, arch: str = "resnet50", weights: str = "IMAGENET1K_V2",
                 device: str = "cuda", crop_hw=(256, 128), batch_size: int = 128) -> None:
        import torch
        import torchvision

        self.device = device if (device == "cpu" or torch.cuda.is_available()) else "cpu"
        self.arch, self.weights_name = arch, weights
        weights_enum = getattr(torchvision.models, f"{_camel(arch)}_Weights")[weights]
        model = getattr(torchvision.models, arch)(weights=weights_enum)
        model.fc = torch.nn.Identity()
        self.model = model.eval().to(self.device)
        self.mean = torch.tensor([0.485, 0.456, 0.406], device=self.device).view(1, 3, 1, 1)
        self.std = torch.tensor([0.229, 0.224, 0.225], device=self.device).view(1, 3, 1, 1)
        self.crop_hw = (int(crop_hw[0]), int(crop_hw[1]))
        self.batch_size = int(batch_size)
        self._torch = torch
        self._weights_url = getattr(weights_enum, "url", None)
        self.dim = None
        self.profile = EmbedProfile()

    def _forward(self, batch_u8: np.ndarray) -> np.ndarray:
        torch = self._torch
        x = torch.from_numpy(batch_u8).to(self.device).permute(0, 3, 1, 2).float() / 255
        x = (x - self.mean) / self.std
        with torch.no_grad(), torch.autocast(
            device_type="cuda", dtype=torch.float16, enabled=self.device.startswith("cuda")
        ):
            feats = self.model(x)
        return feats.float().cpu().numpy()

    def embed(self, img_rgb: np.ndarray, boxes) -> tuple[np.ndarray, np.ndarray]:
        """Return (kept_indices, unit vectors (K, D)) for boxes with a valid crop."""
        crops, keep = [], []
        for i, b in enumerate(boxes):
            c = crop_box(img_rgb, b, self.crop_hw)
            if c is not None:
                crops.append(c)
                keep.append(i)
        if not crops:
            return np.zeros(0, dtype=int), np.zeros((0, self.dim or 0), dtype=np.float32)
        t0 = time.perf_counter()
        feats = []
        for i in range(0, len(crops), self.batch_size):
            feats.append(self._forward(np.stack(crops[i:i + self.batch_size])))
        f = np.concatenate(feats)
        f /= np.maximum(np.linalg.norm(f, axis=1, keepdims=True), 1e-9)
        self.dim = f.shape[1]
        self.profile.crops += len(crops)
        self.profile.seconds += time.perf_counter() - t0
        return np.array(keep, dtype=int), f.astype(np.float32)

    def describe(self) -> dict:
        info = {"backend": "torchvision", "arch": self.arch, "weights": self.weights_name,
                "weights_url": self._weights_url, "crop_hw": list(self.crop_hw),
                "device": self.device, "dim": self.dim}
        try:
            from pathlib import Path

            import torch

            from ml.gate0a.cloud.artifact_manifest import file_sha256

            ckpt_dir = Path(torch.hub.get_dir()) / "checkpoints"
            if self._weights_url:
                p = ckpt_dir / self._weights_url.rsplit("/", 1)[-1]
                if p.exists():
                    info["weights_sha256"] = file_sha256(p)
        except Exception:  # pragma: no cover
            pass
        return info


def _camel(arch: str) -> str:
    return {"resnet18": "ResNet18", "resnet34": "ResNet34", "resnet50": "ResNet50",
            "resnet101": "ResNet101"}[arch]


def load_embedder(cfg: dict, device: str = "cuda") -> tuple[TorchvisionEmbedder, dict]:
    p = cfg["primary"]
    emb = TorchvisionEmbedder(arch=p["arch"], weights=p["weights"], device=device,
                              crop_hw=tuple(cfg["crop_hw"]), batch_size=int(cfg["batch_size"]))
    record = {"name": p["name"], "code_license": p.get("code_license"),
              "provenance_class": p.get("provenance_class"), **emb.describe()}
    return emb, record


def try_load_secondary(cfg: dict, device: str = "cuda"):  # pragma: no cover - optional
    """torchreid OSNet (ImageNet weights) when explicitly enabled; None on failure."""
    s = cfg.get("secondary", {})
    if not s.get("enabled"):
        return None, {"enabled": False}
    try:
        import torch
        import torchreid

        model = torchreid.models.build_model("osnet_x1_0", num_classes=1000, pretrained=True)
        model.eval().to(device if torch.cuda.is_available() else "cpu")
    except Exception as exc:
        return None, {"enabled": True, "loaded": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return model, {"enabled": True, "loaded": True, "name": s.get("name")}
