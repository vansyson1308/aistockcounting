"""Detectors served by OpenCV 5.

Backends (chosen with ``DETECTOR_BACKEND``):

* ``onnx``: the product path. A YOLOX ONNX model (Apache-2.0 detector) run by
  ``cv2.dnn`` with the OpenCV 5 engine selector (``ENGINE_AUTO`` / ``ENGINE_NEW``
  / ``ENGINE_CLASSIC``), a letterbox, YOLOX grid decoding and ``cv2.dnn.NMSBoxes``.
* ``classical``: an OpenCV-only baseline with no learned weights (top-hat
  highlight, Otsu, contours). It makes the agent demo-able before trained
  weights exist, is labelled as a baseline everywhere, and is never reported
  as the product model.
* ``mock``: deterministic fake boxes. For tests only, and only when requested
  explicitly.

A model sidecar ``<model>.json`` describes the export (input size, whether the
grid decode is baked into the graph, the letterbox mode, class names).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

logger = logging.getLogger("app")

ENGINES = {
    "auto": cv2.dnn.ENGINE_AUTO,
    "new": cv2.dnn.ENGINE_NEW,
    "classic": cv2.dnn.ENGINE_CLASSIC,
}


@dataclass(frozen=True)
class Det:
    x: float
    y: float
    w: float
    h: float
    conf: float

    def as_dict(self) -> dict[str, float]:
        return {
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "w": round(self.w, 2),
            "h": round(self.h, 2),
            "conf": round(min(max(self.conf, 0.0), 1.0), 4),
        }


class Detector(Protocol):
    name: str
    version: str

    def detect(self, img_bgr: np.ndarray) -> list[Det]: ...


@dataclass(frozen=True)
class DetectorMeta:
    input_size: tuple[int, int] = (640, 640)  # H, W
    decode_in_model: bool = False
    letterbox: str = "topleft"  # YOLOX pads bottom/right; "center" also supported
    pad_value: int = 114
    swap_rb: bool = False  # YOLOX consumes BGR 0..255
    strides: tuple[int, ...] = (8, 16, 32)
    class_names: tuple[str, ...] = ("item",)
    version: str = "unknown"

    @classmethod
    def load(cls, path: Path | None) -> DetectorMeta:
        if path is None or not path.exists():
            return cls()
        raw = json.loads(path.read_text())
        return cls(
            input_size=tuple(raw.get("input_size", (640, 640))),
            decode_in_model=bool(raw.get("decode_in_model", False)),
            letterbox=str(raw.get("letterbox", "topleft")),
            pad_value=int(raw.get("pad_value", 114)),
            swap_rb=bool(raw.get("swap_rb", False)),
            strides=tuple(raw.get("strides", (8, 16, 32))),
            class_names=tuple(raw.get("class_names", ("item",))),
            version=str(raw.get("version", "unknown")),
        )


def letterbox(
    img: np.ndarray, size: tuple[int, int], mode: str, pad_value: int
) -> tuple[np.ndarray, float, tuple[int, int]]:
    """Resize, keeping the aspect ratio, and pad to ``size`` (H, W).

    Returns (padded, ratio, (pad_x, pad_y)). Original coordinates are
    ``(x - pad_x) / ratio``.
    """
    th, tw = size
    h, w = img.shape[:2]
    r = min(th / h, tw / w)
    nh, nw = int(round(h * r)), int(round(w * r))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    out = np.full((th, tw, 3), pad_value, dtype=np.uint8)
    if mode == "center":
        px, py = (tw - nw) // 2, (th - nh) // 2
    else:
        px, py = 0, 0
    out[py : py + nh, px : px + nw] = resized
    return out, r, (px, py)


def yolox_grid_decode(
    raw: np.ndarray, input_size: tuple[int, int], strides: tuple[int, ...]
) -> np.ndarray:
    """Apply YOLOX grid and stride decoding (as in YOLOX demo_postprocess).

    ``raw`` has shape (N, 5 + C) with [x, y, log w, log h, obj, cls...].
    """
    grids, expanded = [], []
    for stride in strides:
        hs, ws = input_size[0] // stride, input_size[1] // stride
        xv, yv = np.meshgrid(np.arange(ws), np.arange(hs))
        grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
        expanded.append(np.full((hs * ws, 1), stride))
    grid = np.concatenate(grids, 0).astype(np.float32)
    strd = np.concatenate(expanded, 0).astype(np.float32)
    if grid.shape[0] != raw.shape[0]:
        raise ValueError(
            f"model output has {raw.shape[0]} anchors but grid expects {grid.shape[0]}"
        )
    out = raw.astype(np.float32).copy()
    out[:, :2] = (out[:, :2] + grid) * strd
    out[:, 2:4] = np.exp(out[:, 2:4]) * strd
    return out


def nms(dets: list[Det], score_thr: float, iou_thr: float) -> list[Det]:
    if not dets:
        return []
    boxes = [[d.x, d.y, d.w, d.h] for d in dets]
    scores = [float(d.conf) for d in dets]
    keep = cv2.dnn.NMSBoxes(boxes, scores, score_thr, iou_thr)
    return [dets[int(i)] for i in np.array(keep).reshape(-1)]


class OnnxYoloxDetector:
    """YOLOX ONNX served by OpenCV 5 DNN."""

    name = "onnx"

    def __init__(
        self,
        model_path: Path,
        meta: DetectorMeta,
        *,
        engine: str = "auto",
        score_thr: float = 0.25,
        nms_thr: float = 0.45,
    ) -> None:
        self.model_path = model_path
        self.meta = meta
        self.engine = engine
        self.score_thr = score_thr
        self.nms_thr = nms_thr
        self.net = cv2.dnn.readNetFromONNX(str(model_path), ENGINES[engine])
        self.version = meta.version

    def raw_forward(
        self, img_bgr: np.ndarray
    ) -> tuple[np.ndarray, float, tuple[int, int]]:
        padded, ratio, pad = letterbox(
            img_bgr, self.meta.input_size, self.meta.letterbox, self.meta.pad_value
        )
        blob = cv2.dnn.blobFromImage(
            padded, 1.0, (padded.shape[1], padded.shape[0]), swapRB=self.meta.swap_rb
        )
        self.net.setInput(blob)
        out = self.net.forward()
        return np.asarray(out).reshape(-1, out.shape[-1]), ratio, pad

    def detect(self, img_bgr: np.ndarray) -> list[Det]:
        raw, ratio, (px, py) = self.raw_forward(img_bgr)
        pred = (
            raw
            if self.meta.decode_in_model
            else yolox_grid_decode(raw, self.meta.input_size, self.meta.strides)
        )
        obj = pred[:, 4]
        cls = pred[:, 5:] if pred.shape[1] > 5 else np.ones((pred.shape[0], 1))
        scores = obj * cls.max(axis=1)
        keep = scores >= self.score_thr
        pred, scores = pred[keep], scores[keep]
        h, w = img_bgr.shape[:2]
        dets: list[Det] = []
        for (cx, cy, bw, bh), s in zip(pred[:, :4], scores, strict=True):
            x0 = max(0.0, (cx - bw / 2 - px) / ratio)
            y0 = max(0.0, (cy - bh / 2 - py) / ratio)
            x1 = min(float(w), (cx + bw / 2 - px) / ratio)
            y1 = min(float(h), (cy + bh / 2 - py) / ratio)
            if x1 - x0 < 1 or y1 - y0 < 1:
                continue
            dets.append(
                Det(float(x0), float(y0), float(x1 - x0), float(y1 - y0), float(s))
            )
        return nms(dets, self.score_thr, self.nms_thr)


class ClassicalDetector:
    """OpenCV-only baseline for bright metal items on a darker tray.

    Top-hat (bright detail smaller than the structuring element), then an Otsu
    threshold, closing, external contours, and area and shape filters. The
    confidence is a heuristic built from local contrast and solidity. It is not
    calibrated.
    """

    name = "classical"
    version = "classical-baseline-1"

    def __init__(
        self,
        min_area_px: float = 60.0,
        max_area_frac: float = 0.03,
        input_side: int = 1280,
    ) -> None:
        # Like a CNN, the baseline works at a fixed input resolution, so items
        # that are tiny in a full-frame shot fall under ``min_area_px``.
        self.min_area_px = min_area_px
        self.max_area_frac = max_area_frac
        self.input_side = input_side

    def detect(self, img_bgr: np.ndarray) -> list[Det]:
        h, w = img_bgr.shape[:2]
        scale = self.input_side / float(max(h, w))
        work = cv2.resize(
            img_bgr,
            (round(w * scale), round(h * scale)),
            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
        )
        gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
        k = max(15, (min(gray.shape[:2]) // 10) | 1)
        tophat = cv2.morphologyEx(
            gray, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        )
        tophat = cv2.GaussianBlur(tophat, (3, 3), 0)
        thr, mask = cv2.threshold(tophat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if thr < 25:  # nearly flat image: Otsu would split noise
            _, mask = cv2.threshold(tophat, 25, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        )
        area_img = float(gray.shape[0] * gray.shape[1])
        # A bright tray rim or table strip along the frame edge would enclose
        # every item in one external contour. Drop large border-touching
        # components first.
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        gh, gw = mask.shape
        for i in range(1, n):
            x, y, bw, bh, _a = stats[i]
            touches = x == 0 or y == 0 or x + bw >= gw or y + bh >= gh
            if touches and bw * bh > self.max_area_frac * area_img:
                mask[labels == i] = 0
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        dets: list[Det] = []
        for cnt in contours:
            x, y, bw, bh = cv2.boundingRect(cnt)
            box_area = float(bw * bh)
            if not (self.min_area_px <= box_area <= self.max_area_frac * area_img):
                continue
            aspect = max(bw, bh) / max(1.0, min(bw, bh))
            if aspect > 4.0:
                continue
            hull_area = float(cv2.contourArea(cv2.convexHull(cnt))) or 1.0
            solidity = float(cv2.contourArea(cnt)) / hull_area
            contrast = float(np.mean(tophat[y : y + bh, x : x + bw])) / 255.0
            conf = float(np.clip(0.35 + 0.9 * contrast + 0.25 * solidity, 0.05, 0.97))
            dets.append(Det(x / scale, y / scale, bw / scale, bh / scale, conf))
        return nms(dets, 0.05, 0.5)


class MockDetector:
    """Deterministic fake boxes. Tests only."""

    name = "mock"
    version = "mock"

    def detect(self, img_bgr: np.ndarray) -> list[Det]:
        seed = int(hashlib.sha256(img_bgr.tobytes()).hexdigest()[:8], 16)
        count = (seed % 4) + 2
        return [
            Det(20.0 + i * 35, 25.0 + i * 20, 40.0, 30.0, round(0.75 + i * 0.03, 2))
            for i in range(count)
        ]


@dataclass
class DetectorStatus:
    backend: str
    ready: bool
    reason: str = ""
    model_path: str | None = None
    model_sha256: str | None = None
    engine: str | None = None
    version: str | None = None
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "backend": self.backend,
            "ready": self.ready,
            "reason": self.reason,
            "model_path": self.model_path,
            "model_sha256": self.model_sha256,
            "engine": self.engine,
            "version": self.version,
            "is_baseline": self.backend == "classical",
            "is_mock": self.backend == "mock",
        }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_detector(
    backend: str,
    *,
    model_path: str,
    meta_path: str | None = None,
    engine: str = "auto",
    score_thr: float = 0.25,
    nms_thr: float = 0.45,
) -> tuple[Detector | None, DetectorStatus]:
    backend = backend.lower().strip()
    if backend == "mock":
        logger.warning("detector backend is MOCK (explicitly requested)")
        return MockDetector(), DetectorStatus(
            "mock", True, "explicit mock", version="mock"
        )
    if backend == "classical":
        logger.warning(
            "detector backend is the CLASSICAL baseline (no learned weights)"
        )
        det = ClassicalDetector()
        return det, DetectorStatus(
            "classical", True, "opencv baseline", version=det.version
        )
    if backend != "onnx":
        return None, DetectorStatus(backend, False, f"unknown backend {backend!r}")

    path = Path(model_path)
    if not path.exists():
        logger.error(
            "ONNX model not found at %s; the detector is NOT ready (no silent mock). "
            "Run scripts/fetch_model.sh or set DETECTOR_BACKEND=classical.",
            path,
        )
        return None, DetectorStatus(
            "onnx", False, "model file missing", model_path=str(path), engine=engine
        )
    meta_file = Path(meta_path) if meta_path else path.with_suffix(".json")
    meta = DetectorMeta.load(meta_file)
    try:
        det = OnnxYoloxDetector(
            path, meta, engine=engine, score_thr=score_thr, nms_thr=nms_thr
        )
    except Exception as exc:  # cv2.error on a malformed graph
        logger.exception("failed to load ONNX model %s", path)
        return None, DetectorStatus(
            "onnx",
            False,
            f"load failed: {exc}"[:300],
            model_path=str(path),
            engine=engine,
        )
    return det, DetectorStatus(
        "onnx",
        True,
        "loaded",
        model_path=str(path),
        model_sha256=sha256_file(path),
        engine=engine,
        version=meta.version,
    )
