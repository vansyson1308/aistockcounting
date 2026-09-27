"""Drawing helpers for evidence images (OpenCV drawing primitives only)."""

from __future__ import annotations

from collections.abc import Iterable

import cv2
import numpy as np

from app.services.detector_cv import Det

GREEN = (80, 200, 80)
ORANGE = (0, 165, 255)
RED = (40, 40, 230)
CYAN = (230, 200, 0)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)


def fit(img: np.ndarray, max_side: int = 1280) -> tuple[np.ndarray, float]:
    h, w = img.shape[:2]
    s = min(1.0, max_side / float(max(h, w)))
    if s == 1.0:
        return img.copy(), 1.0
    return (
        cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA),
        s,
    )


def label(img: np.ndarray, text: str, org: tuple[int, int], scale: float = 0.6) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), base = cv2.getTextSize(text, font, scale, 1)
    x, y = org
    cv2.rectangle(img, (x, y - th - base - 2), (x + tw + 4, y + 2), BLACK, -1)
    cv2.putText(img, text, (x + 2, y - base), font, scale, WHITE, 1, cv2.LINE_AA)


def draw_dets(
    img: np.ndarray,
    dets: Iterable[Det],
    scale: float = 1.0,
    uncertain: tuple[float, float] = (0.25, 0.5),
) -> np.ndarray:
    for d in dets:
        color = ORANGE if uncertain[0] <= d.conf < uncertain[1] else GREEN
        p0 = (int(d.x * scale), int(d.y * scale))
        p1 = (int((d.x + d.w) * scale), int((d.y + d.h) * scale))
        cv2.rectangle(img, p0, p1, color, 2)
    return img


def draw_rects(
    img: np.ndarray,
    rects: Iterable[tuple[int, int, int, int]],
    color,
    scale: float = 1.0,
) -> np.ndarray:
    for x, y, w, h in rects:
        p0 = (int(x * scale), int(y * scale))
        p1 = (int((x + w) * scale), int((y + h) * scale))
        cv2.rectangle(img, p0, p1, color, 3)
    return img


def banner(img: np.ndarray, lines: list[str]) -> np.ndarray:
    """Stack a dark text banner above ``img``."""
    h = 28 * len(lines) + 12
    top = np.zeros((h, img.shape[1], 3), np.uint8)
    for i, line in enumerate(lines):
        cv2.putText(
            top,
            line,
            (10, 28 * (i + 1)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            WHITE,
            1,
            cv2.LINE_AA,
        )
    return np.vstack([top, img])


def side_by_side(a: np.ndarray, b: np.ndarray, height: int = 480) -> np.ndarray:
    def rh(x: np.ndarray) -> np.ndarray:
        s = height / x.shape[0]
        return cv2.resize(x, (max(1, round(x.shape[1] * s)), height))

    gap = np.full((height, 8, 3), 255, np.uint8)
    return np.hstack([rh(a), gap, rh(b)])


def mosaic(tiles: list[np.ndarray], cell: int = 240, cols: int = 4) -> np.ndarray:
    if not tiles:
        return np.zeros((cell, cell, 3), np.uint8)
    rows = (len(tiles) + cols - 1) // cols
    out = np.full((rows * cell, min(cols, len(tiles)) * cell, 3), 30, np.uint8)
    for i, t in enumerate(tiles):
        s = cell / max(t.shape[:2])
        r = cv2.resize(t, (max(1, int(t.shape[1] * s)), max(1, int(t.shape[0] * s))))
        y, x = (i // cols) * cell, (i % cols) * cell
        out[y : y + r.shape[0], x : x + r.shape[1]] = r
    return out
