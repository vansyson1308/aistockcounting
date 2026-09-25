"""Image decode/encode helpers (OpenCV imgcodecs)."""

from __future__ import annotations

import cv2
import numpy as np


class ImageDecodeError(ValueError):
    pass


def decode_image(payload: bytes) -> np.ndarray:
    """Decode JPEG/PNG bytes to a BGR uint8 array, honouring EXIF orientation."""
    buf = np.frombuffer(payload, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        raise ImageDecodeError("could not decode image")
    return img


def encode_jpeg(img: np.ndarray, quality: int = 88) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    if not ok:
        raise ValueError("JPEG encode failed")
    return buf.tobytes()


def ensure_bgr(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return img


def resize_max_side(img: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    """Downscale so the longest side is at most ``max_side``. Returns (img, scale)."""
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= max_side:
        return img, 1.0
    scale = max_side / float(longest)
    out = cv2.resize(
        img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA
    )
    return out, scale


def as_image(image: bytes | np.ndarray) -> np.ndarray:
    if isinstance(image, (bytes, bytearray, memoryview)):
        return decode_image(bytes(image))
    return ensure_bgr(image)
