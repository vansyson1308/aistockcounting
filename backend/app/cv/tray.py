"""Tray localisation: find the tray quadrilateral and its coverage of the frame.

Two OpenCV strategies, the first success wins:
1. Edge contours: Canny, dilate, external contours, then ``approxPolyDP`` down
   to a convex 4-gon.
2. Intensity segmentation: an Otsu threshold (both polarities), the largest
   connected component, then ``minAreaRect`` and ``boxPoints``.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.cv.imageio import resize_max_side

WORK_SIDE = 800
MIN_QUAD_FRAC = 0.12
FULL_FRAME_FRAC = 0.95


@dataclass(frozen=True)
class TrayLocation:
    quad: np.ndarray | None  # 4x2 float32 in input-image coords (TL, TR, BR, BL)
    coverage: float  # tray area / image area, 0..1
    method: str  # "contour" | "segmentation" | "none"


def order_quad(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as TL, TR, BR, BL."""
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
        dtype=np.float32,
    )


def _quad_from_contours(gray: np.ndarray) -> np.ndarray | None:
    h, w = gray.shape[:2]
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 120)
    edges = cv2.dilate(edges, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    img_area = float(h * w)
    for cnt in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        area = cv2.contourArea(cnt)
        if area < MIN_QUAD_FRAC * img_area:
            break
        peri = cv2.arcLength(cnt, True)
        for eps in (0.02, 0.03, 0.05):
            approx = cv2.approxPolyDP(cnt, eps * peri, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                # reject a quad that is just the image border
                x, y, bw, bh = cv2.boundingRect(approx)
                if bw * bh >= 0.97 * img_area:
                    continue
                return order_quad(approx)
    return None


def _quad_from_segmentation(gray: np.ndarray) -> tuple[np.ndarray | None, float]:
    h, w = gray.shape[:2]
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    best_area, best_quad = 0.0, None
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    for mask in (otsu, cv2.bitwise_not(otsu)):
        closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
        if n <= 1:
            continue
        idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        x, y, bw, bh, area = stats[idx]
        # A component touching 3+ borders is the table around a tray, unless
        # it fills essentially the whole frame (a close-up of the tray).
        touches = int(x == 0) + int(y == 0) + int(x + bw >= w) + int(y + bh >= h)
        if touches >= 3 and area < FULL_FRAME_FRAC * h * w:
            continue
        if area > best_area:
            comp = (labels == idx).astype(np.uint8)
            cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not cnts:
                continue
            rect = cv2.minAreaRect(max(cnts, key=cv2.contourArea))
            best_area, best_quad = float(area), order_quad(cv2.boxPoints(rect))
    return best_quad, best_area / float(h * w)


def locate_tray(img_bgr: np.ndarray) -> TrayLocation:
    small, scale = resize_max_side(img_bgr, WORK_SIDE)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    img_area = float(gray.shape[0] * gray.shape[1])

    quad = _quad_from_contours(gray)
    if quad is not None:
        coverage = float(cv2.contourArea(quad)) / img_area
        return TrayLocation(quad / scale, min(coverage, 1.0), "contour")

    seg_quad, seg_cov = _quad_from_segmentation(gray)
    if seg_quad is not None and seg_cov >= MIN_QUAD_FRAC:
        return TrayLocation(seg_quad / scale, min(seg_cov, 1.0), "segmentation")
    return TrayLocation(None, float(seg_cov), "none")


def quad_mask(shape: tuple[int, int], quad: np.ndarray | None) -> np.ndarray:
    """A uint8 mask of the tray quad (the full frame when quad is None)."""
    h, w = shape
    if quad is None:
        return np.full((h, w), 255, np.uint8)
    mask = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(mask, quad.astype(np.int32), 255)
    return mask
