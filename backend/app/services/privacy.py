"""Blur faces before anything is stored (SPEC §8).

Uses OpenCV's ``FaceDetectorYN`` with the bundled YuNet ONNX model
(opencv_zoo, MIT). OpenCV 5 moved the Haar cascades out of the main wheel,
so there is no cascade fallback. If the model cannot load, the call
returns the image unchanged and reports ``available=False`` so the caller
can record it in the trace.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger("app")

BUNDLED_YUNET = (
    Path(__file__).resolve().parents[1] / "assets" / "face_detection_yunet_2023mar.onnx"
)
DETECT_SIDE = 640


@dataclass(frozen=True)
class FaceBlurResult:
    image: np.ndarray
    faces: int
    available: bool


class FaceBlurrer:
    _instance: FaceBlurrer | None = None
    _lock = threading.Lock()

    def __init__(self, model_path: Path, score_threshold: float = 0.7) -> None:
        self.model_path = model_path
        self.detector = cv2.FaceDetectorYN.create(
            str(model_path), "", (DETECT_SIDE, DETECT_SIDE), score_threshold, 0.3, 50
        )

    @classmethod
    def get(cls, model_path: str = "") -> FaceBlurrer | None:
        with cls._lock:
            if cls._instance is None:
                path = Path(model_path) if model_path else BUNDLED_YUNET
                try:
                    cls._instance = FaceBlurrer(path)
                except Exception:
                    logger.exception("face detector unavailable (%s)", path)
                    return None
            return cls._instance

    def faces(self, img_bgr: np.ndarray) -> np.ndarray:
        h, w = img_bgr.shape[:2]
        scale = min(1.0, DETECT_SIDE / max(h, w))
        small = (
            cv2.resize(img_bgr, (round(w * scale), round(h * scale)))
            if scale < 1
            else img_bgr
        )
        with self._lock:  # FaceDetectorYN keeps per-instance state
            self.detector.setInputSize((small.shape[1], small.shape[0]))
            _, faces = self.detector.detect(small)
        if faces is None:
            return np.zeros((0, 4), np.float32)
        return faces[:, :4] / scale

    def blur(self, img_bgr: np.ndarray) -> FaceBlurResult:
        boxes = self.faces(img_bgr)
        out = img_bgr.copy()
        h, w = out.shape[:2]
        for x, y, bw, bh in boxes:
            pad = 0.25
            x0 = int(max(0, x - pad * bw))
            y0 = int(max(0, y - pad * bh))
            x1 = int(min(w, x + (1 + pad) * bw))
            y1 = int(min(h, y + (1 + pad) * bh))
            if x1 <= x0 or y1 <= y0:
                continue
            roi = out[y0:y1, x0:x1]
            k = max(15, (max(x1 - x0, y1 - y0) // 3) | 1)
            out[y0:y1, x0:x1] = cv2.GaussianBlur(roi, (k, k), 0)
        return FaceBlurResult(out, len(boxes), True)


def blur_faces(img_bgr: np.ndarray, model_path: str = "") -> FaceBlurResult:
    blurrer = FaceBlurrer.get(model_path)
    if blurrer is None:
        return FaceBlurResult(img_bgr, 0, False)
    return blurrer.blur(img_bgr)


def sanitize_upload(
    payload: bytes, *, enabled: bool, model_path: str = ""
) -> tuple[bytes, int]:
    """Blur faces in an uploaded image before it is stored.

    Returns (bytes to store, number of faces blurred). When no face is found
    the original bytes are kept, so there is no re-encode loss.
    """
    if not enabled:
        return payload, 0
    from app.cv.imageio import decode_image, encode_jpeg

    img = decode_image(payload)
    result = blur_faces(img, model_path)
    if result.faces == 0:
        return payload, 0
    logger.info("blurred %d face(s) before storage", result.faces)
    return encode_jpeg(result.image, 92), result.faces
