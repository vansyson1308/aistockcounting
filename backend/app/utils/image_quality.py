"""Image quality assessment with OpenCV 5.

Keeps the original return shape (``ImageQuality(score, flags, metrics)``) so the
truth-layer routes keep working. The metrics are computed on a copy resized so
the longest side is 1024 px, which keeps the thresholds independent of phone
resolution.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.cv.imageio import as_image, resize_max_side
from app.cv.tray import locate_tray, quad_mask

WORK_SIDE = 1024

# Flag thresholds. These are provisional until calibrated on the real
# validation split (docs/competition/SPEC.md §4.4).
LOW_LIGHT_P99 = 90.0
OVEREXPOSED_BRIGHTNESS = 225.0
GLARE_RATIO_FLAG = 0.04
BLUR_VAR_FLAG = 60.0
LOW_CONTRAST = 18.0
TRAY_COVERAGE_FLAG = 0.15

GLARE_V_MIN = 245
GLARE_S_MAX = 40


@dataclass(frozen=True)
class ImageQuality:
    score: float
    flags: list[str]
    metrics: dict[str, float]


def glare_mask(img_bgr: np.ndarray) -> np.ndarray:
    """Specular highlight mask: very bright and nearly unsaturated (HSV)."""
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 0, GLARE_V_MIN), (180, GLARE_S_MAX, 255))
    # ignore isolated specks (a tiny glint on a ring is not glare)
    return cv2.morphologyEx(
        mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    )


def compute_metrics(img_bgr: np.ndarray) -> tuple[dict[str, float], np.ndarray | None]:
    img, _ = resize_max_side(img_bgr, WORK_SIDE)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    tray = locate_tray(img)
    region = quad_mask(gray.shape[:2], tray.quad)
    region_px = max(int(np.count_nonzero(region)), 1)

    mean, std = cv2.meanStdDev(gray)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    edge_energy = float(np.mean(cv2.magnitude(gx, gy))) / 4.0

    # Blur is measured inside the tray (eroded, so the tray border itself does
    # not count), where the items are.
    k = max(3, int(0.03 * min(gray.shape[:2])) | 1)
    inner = cv2.erode(region, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    if np.count_nonzero(inner) < 0.05 * gray.size:
        inner = region
    lap = cv2.Laplacian(gray, cv2.CV_64F, ksize=3)
    _, lap_std = cv2.meanStdDev(lap, mask=inner)
    blur_var = float(lap_std[0][0]) ** 2
    p99 = float(np.percentile(gray, 99))

    gmask = cv2.bitwise_and(glare_mask(img), region)
    glare_ratio = float(np.count_nonzero(gmask)) / region_px

    hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).ravel() / gray.size
    metrics = {
        "brightness": round(float(mean[0][0]), 2),
        "brightness_p99": round(p99, 2),
        "contrast": round(float(std[0][0]), 2),
        "edge_energy": round(edge_energy, 2),
        "glare_ratio": round(glare_ratio, 4),
        "blur_var": round(blur_var, 2),
        "tray_coverage": round(float(tray.coverage), 4),
        "clip_low": round(float(hist[:8].sum()), 4),
        "clip_high": round(float(hist[248:].sum()), 4),
    }
    quad = None if tray.quad is None else tray.quad.astype(np.float32)
    return metrics, quad


def assess_image_quality(image: bytes | np.ndarray) -> ImageQuality:
    img = as_image(image)
    metrics, _ = compute_metrics(img)

    flags: list[str] = []
    # Trays are often dark velvet, so low light is judged on the bright end of
    # the histogram (metal items and the table), not on the mean.
    if metrics["brightness_p99"] < LOW_LIGHT_P99:
        flags.append("low_light")
    if (
        metrics["brightness"] > OVEREXPOSED_BRIGHTNESS
        or metrics["glare_ratio"] > GLARE_RATIO_FLAG
    ):
        flags.append("glare")
    if metrics["blur_var"] < BLUR_VAR_FLAG or metrics["contrast"] < LOW_CONTRAST:
        flags.append("blurry")
    if metrics["tray_coverage"] < TRAY_COVERAGE_FLAG:
        flags.append("tray_not_found")

    score = 1.0
    score -= 0.25 if "low_light" in flags else 0
    score -= 0.25 if "glare" in flags else 0
    score -= 0.3 if "blurry" in flags else 0
    score -= 0.2 if "tray_not_found" in flags else 0
    score = max(0.0, round(score, 2))
    return ImageQuality(score=score, flags=flags, metrics=metrics)
