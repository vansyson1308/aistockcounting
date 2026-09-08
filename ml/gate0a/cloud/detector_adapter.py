"""Real detector adapter: D-FINE (primary) / RT-DETRv2 (fallback) via
`transformers`, run as tiled inference on the native panorama resolution.

Geometry (tile planning, tile→frame mapping, cross-tile NMS, MOT det rows)
is pure numpy and unit-tested; the model call is isolated in `HFDetector`.
Provenance (hub id, revision, weights sha256, license tag) is recorded for
the artifact manifest. Weights are RESEARCH-DIAGNOSTIC class (COCO-trained).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

Tile = tuple[int, int, int, int]  # x0, y0, x1, y1 (frame pixels)


def plan_tiles(width: int, height: int, tile_px: int, overlap_px: int) -> list[Tile]:
    """SAHI-style grid: fixed-size tiles, last tile aligned to the far edge."""
    tile_px = int(tile_px)
    step = max(1, tile_px - int(overlap_px))

    def starts(extent: int) -> list[int]:
        if extent <= tile_px:
            return [0]
        s = list(range(0, extent - tile_px + 1, step))
        if s[-1] + tile_px < extent:
            s.append(extent - tile_px)
        return s

    tiles = []
    for y0 in starts(height):
        for x0 in starts(width):
            tiles.append((x0, y0, min(x0 + tile_px, width), min(y0 + tile_px, height)))
    return tiles


def nms_numpy(boxes: np.ndarray, scores: np.ndarray, iou_thr: float) -> np.ndarray:
    """Greedy NMS on xyxy boxes → kept indices (score-descending)."""
    if len(boxes) == 0:
        return np.zeros(0, dtype=int)
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    order = np.argsort(-scores)
    keep = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        union = areas[i] + areas[rest] - inter
        iou = np.where(union > 0, inter / union, 0.0)
        order = rest[iou <= iou_thr]
    return np.array(keep, dtype=int)


def merge_tiles(
    per_tile: list[tuple[np.ndarray, np.ndarray]], tiles: list[Tile], nms_iou: float
) -> tuple[np.ndarray, np.ndarray]:
    """Map tile-local xyxy boxes to frame coordinates and NMS across tiles."""
    boxes_all, scores_all = [], []
    for (boxes, scores), (x0, y0, _x1, _y1) in zip(per_tile, tiles, strict=True):
        if len(boxes) == 0:
            continue
        b = np.asarray(boxes, dtype=float).copy()
        b[:, [0, 2]] += x0
        b[:, [1, 3]] += y0
        boxes_all.append(b)
        scores_all.append(np.asarray(scores, dtype=float))
    if not boxes_all:
        return np.zeros((0, 4)), np.zeros(0)
    boxes = np.concatenate(boxes_all)
    scores = np.concatenate(scores_all)
    keep = nms_numpy(boxes, scores, nms_iou)
    return boxes[keep], scores[keep]


def to_mot_det_rows(frame: int, boxes: np.ndarray, scores: np.ndarray) -> list[tuple]:
    rows = []
    for b, s in zip(boxes, scores, strict=True):
        rows.append((int(frame), -1, float(b[0]), float(b[1]),
                     float(b[2] - b[0]), float(b[3] - b[1]), float(s)))
    return rows


@dataclass
class DetectorProfile:
    frames: int = 0
    tiles: int = 0
    seconds: float = 0.0
    tiles_per_frame: float = 0.0
    fps: float = 0.0
    peak_vram_gb: float | None = None
    per_window: dict = field(default_factory=dict)

    def finish(self) -> dict:
        self.tiles_per_frame = round(self.tiles / self.frames, 2) if self.frames else 0.0
        self.fps = round(self.frames / self.seconds, 3) if self.seconds else 0.0
        return {
            "frames": self.frames, "tiles": self.tiles, "seconds": round(self.seconds, 2),
            "tiles_per_frame": self.tiles_per_frame, "detector_fps_measured": self.fps,
            "peak_vram_gb": self.peak_vram_gb, "per_window": self.per_window,
        }


class HFDetector:
    """One `transformers` object-detection checkpoint, batched over RGB tiles."""

    def __init__(self, hf_id: str, device: str = "cuda", fp16: bool = True,
                 person_label: str = "person", score_floor: float = 0.05,
                 input_px: int = 640, token: str | None = None) -> None:
        import torch
        from transformers import AutoImageProcessor, AutoModelForObjectDetection

        self.hf_id = hf_id
        self.device = device if (device == "cpu" or torch.cuda.is_available()) else "cpu"
        self.fp16 = bool(fp16) and self.device.startswith("cuda")
        self.score_floor = float(score_floor)
        self.processor = AutoImageProcessor.from_pretrained(
            hf_id, token=token, size={"height": input_px, "width": input_px}
        )
        self.model = AutoModelForObjectDetection.from_pretrained(hf_id, token=token)
        self.model.to(self.device).eval()
        id2label = {int(k): str(v).lower() for k, v in self.model.config.id2label.items()}
        matches = [k for k, v in id2label.items() if v == person_label.lower()]
        if not matches:
            raise ValueError(f"{hf_id}: label {person_label!r} not in id2label")
        self.person_id = matches[0]
        self.input_px = int(input_px)
        self._torch = torch

    def detect_tiles(self, tiles_rgb: list[np.ndarray]) -> list[tuple[np.ndarray, np.ndarray]]:
        torch = self._torch
        inputs = self.processor(images=list(tiles_rgb), return_tensors="pt")
        pixel_values = inputs["pixel_values"].to(self.device)
        with torch.no_grad(), torch.autocast(
            device_type="cuda", dtype=torch.float16, enabled=self.fp16
        ):
            outputs = self.model(pixel_values=pixel_values)
        sizes = torch.tensor([[t.shape[0], t.shape[1]] for t in tiles_rgb])
        results = self.processor.post_process_object_detection(
            outputs, threshold=self.score_floor, target_sizes=sizes
        )
        out = []
        for r in results:
            labels = r["labels"].detach().cpu().numpy()
            keep = labels == self.person_id
            boxes = r["boxes"].detach().float().cpu().numpy()[keep]
            scores = r["scores"].detach().float().cpu().numpy()[keep]
            out.append((boxes, scores))
        return out

    def describe(self) -> dict:
        info: dict = {"hf_id": self.hf_id, "device": self.device,
                      "precision": "fp16-autocast" if self.fp16 else "fp32",
                      "person_label_id": self.person_id, "model_input_px": self.input_px}
        try:
            from huggingface_hub import HfApi, hf_hub_download

            mi = HfApi().model_info(self.hf_id)
            info["revision"] = getattr(mi, "sha", None)
            card = getattr(mi, "card_data", None) or getattr(mi, "cardData", None)
            info["license_tag"] = (card.get("license") if isinstance(card, dict)
                                   else getattr(card, "license", None))
            info["tags"] = list(getattr(mi, "tags", []) or [])[:20]
            from ml.gate0a.cloud.artifact_manifest import file_sha256

            for fname in ("model.safetensors", "pytorch_model.bin"):
                try:
                    p = hf_hub_download(self.hf_id, fname, revision=info.get("revision"))
                    info["weights_file"] = fname
                    info["weights_sha256"] = file_sha256(p)
                    break
                except Exception:
                    continue
        except Exception as exc:  # pragma: no cover - network dependent
            info["provenance_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        try:
            import transformers

            info["transformers_version"] = transformers.__version__
            info["model_class"] = type(self.model).__name__
        except Exception:  # pragma: no cover
            pass
        return info


class TiledDetector:
    """Frame-level detector: plan tiles once per resolution, batch, merge."""

    def __init__(self, backend, cfg: dict) -> None:
        self.backend = backend
        self.tile_px = int(cfg["tile_px"])
        self.overlap_px = int(cfg["overlap_px"])
        self.batch_tiles = int(cfg["batch_tiles"])
        self.nms_iou = float(cfg["nms_iou"])
        self._plan_cache: dict[tuple[int, int], list[Tile]] = {}
        self.profile = DetectorProfile()

    def tiles_for(self, width: int, height: int) -> list[Tile]:
        key = (width, height)
        if key not in self._plan_cache:
            self._plan_cache[key] = plan_tiles(width, height, self.tile_px, self.overlap_px)
        return self._plan_cache[key]

    def detect_frame(self, img_rgb: np.ndarray, window: str = "") -> tuple[np.ndarray, np.ndarray]:
        h, w = img_rgb.shape[:2]
        tiles = self.tiles_for(w, h)
        t0 = time.perf_counter()
        per_tile: list[tuple[np.ndarray, np.ndarray]] = []
        for i in range(0, len(tiles), self.batch_tiles):
            chunk = tiles[i:i + self.batch_tiles]
            crops = [img_rgb[y0:y1, x0:x1] for (x0, y0, x1, y1) in chunk]
            per_tile.extend(self.backend.detect_tiles(crops))
        boxes, scores = merge_tiles(per_tile, tiles, self.nms_iou)
        dt = time.perf_counter() - t0
        self.profile.frames += 1
        self.profile.tiles += len(tiles)
        self.profile.seconds += dt
        if window:
            pw = self.profile.per_window.setdefault(window, {"frames": 0, "seconds": 0.0})
            pw["frames"] += 1
            pw["seconds"] += dt
        return boxes, scores

    def describe(self) -> dict:
        d = self.backend.describe() if hasattr(self.backend, "describe") else {}
        d.update({"tile_px": self.tile_px, "overlap_px": self.overlap_px,
                  "batch_tiles": self.batch_tiles, "nms_iou": self.nms_iou})
        return d


def load_detector(cfg: dict, device: str = "cuda", token: str | None = None) -> tuple[TiledDetector, dict]:
    """Primary D-FINE, fallback RT-DETRv2 with the concrete failure recorded."""
    attempts = []
    for key in ("primary", "fallback"):
        spec = cfg[key]
        try:
            backend = HFDetector(
                spec["hf_id"], device=device, fp16=bool(cfg.get("fp16", True)),
                person_label=cfg.get("person_label", "person"),
                score_floor=float(cfg.get("score_floor", 0.05)),
                input_px=int(cfg.get("model_input_px", 640)), token=token,
            )
            det = TiledDetector(backend, cfg)
            record = {"selected": key, "name": spec["name"], "hf_id": spec["hf_id"],
                      "code_license": spec.get("code_license"),
                      "weights_note": spec.get("weights_note"),
                      "provenance_class": spec.get("provenance_class"),
                      "attempts": attempts, **det.describe()}
            return det, record
        except Exception as exc:
            attempts.append({"candidate": key, "hf_id": spec["hf_id"],
                             "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
    raise RuntimeError(f"no detector could be loaded: {attempts}")
