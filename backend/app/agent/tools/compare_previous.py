"""compare_previous: align yesterday's approved photo to today's and diff them.

1. ORB keypoints + brute-force Hamming kNN matching with the ratio test
   (SIFT + L2 as a fallback when ORB finds too few inliers; AKAZE is not in
   the OpenCV 5.0 main wheel, see DECISIONS D-008);
2. ``cv2.findHomography`` with RANSAC, then ``cv2.warpPerspective`` of the
   previous image into today's frame;
3. CLAHE-normalised grey ``cv2.absdiff`` plus the LAB chroma difference,
   Otsu threshold, morphological open/close and
   ``connectedComponentsWithStats`` to get the changed regions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from app.agent.tools.draw import RED, banner, draw_rects
from app.agent.tools.types import Rect, ToolResultBase

WORK_SIDE = 1024
MIN_INLIERS = 15


@dataclass(frozen=True)
class CompareResult(ToolResultBase):
    aligned: bool
    method: str
    matches: int
    inliers: int
    changed_ratio: float
    regions: tuple[Rect, ...]  # in the *current* image's original coordinates
    homography: np.ndarray | None  # prev -> curr (original coords)

    def outputs(self) -> dict[str, Any]:
        return {
            "aligned": self.aligned,
            "method": self.method,
            "matches": self.matches,
            "inliers": self.inliers,
            "changed_ratio": round(self.changed_ratio, 4),
            "changed_regions": [list(r) for r in self.regions],
        }


def _resize(img: np.ndarray) -> tuple[np.ndarray, float]:
    h, w = img.shape[:2]
    s = min(1.0, WORK_SIDE / max(h, w))
    if s == 1.0:
        return img, 1.0
    return (
        cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA),
        s,
    )


def _match(
    g_prev: np.ndarray, g_curr: np.ndarray, method: str
) -> tuple[np.ndarray | None, int, int]:
    if method == "orb":
        feat = cv2.ORB_create(nfeatures=4000, fastThreshold=10)
        norm = cv2.NORM_HAMMING
    else:
        feat = cv2.SIFT_create(nfeatures=3000)
        norm = cv2.NORM_L2
    kp1, d1 = feat.detectAndCompute(g_prev, None)
    kp2, d2 = feat.detectAndCompute(g_curr, None)
    if d1 is None or d2 is None or len(kp1) < 8 or len(kp2) < 8:
        return None, 0, 0
    knn = cv2.BFMatcher(norm).knnMatch(d1, d2, k=2)
    good = [p[0] for p in knn if len(p) == 2 and p[0].distance < 0.75 * p[1].distance]
    if len(good) < 8:
        return None, len(good), 0
    src = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    inliers = int(mask.sum()) if mask is not None else 0
    return H, len(good), inliers


def compare_previous(
    current: np.ndarray, previous: np.ndarray, min_region_frac: float = 0.0008
) -> CompareResult:
    cur, sc = _resize(current)
    prv, sp = _resize(previous)
    g_cur = cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY)
    g_prv = cv2.cvtColor(prv, cv2.COLOR_BGR2GRAY)

    H, matches, inliers, method = None, 0, 0, "orb"
    for m in ("orb", "sift"):
        H, matches, inliers = _match(g_prv, g_cur, m)
        method = m
        if H is not None and inliers >= MIN_INLIERS:
            break
    if H is None or inliers < MIN_INLIERS:
        ev = banner(
            cur.copy(),
            [f"compare_previous  alignment FAILED ({method}, inliers={inliers})"],
        )
        return CompareResult(ev, False, method, matches, inliers, 0.0, (), None)

    hh, ww = g_cur.shape
    warped = cv2.warpPerspective(prv, H, (ww, hh))
    valid = cv2.warpPerspective(np.full(g_prv.shape, 255, np.uint8), H, (ww, hh))
    valid = cv2.erode(valid, cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15)))

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    a = clahe.apply(cv2.GaussianBlur(g_cur, (5, 5), 0))
    b = clahe.apply(
        cv2.GaussianBlur(cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    )
    diff = cv2.absdiff(a, b)
    lab_a = cv2.cvtColor(cv2.GaussianBlur(cur, (5, 5), 0), cv2.COLOR_BGR2LAB)
    lab_b = cv2.cvtColor(cv2.GaussianBlur(warped, (5, 5), 0), cv2.COLOR_BGR2LAB)
    chroma = cv2.max(
        cv2.absdiff(lab_a[..., 1], lab_b[..., 1]),
        cv2.absdiff(lab_a[..., 2], lab_b[..., 2]),
    )
    diff = cv2.max(diff, cv2.multiply(chroma, 2))
    diff = cv2.bitwise_and(diff, valid)

    otsu, _ = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, mask = cv2.threshold(diff, max(35.0, otsu), 255, cv2.THRESH_BINARY)
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    )
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    )
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    min_area = min_region_frac * hh * ww
    regions_small = [
        tuple(int(v) for v in stats[i, :4])
        for i in range(1, n)
        if stats[i, cv2.CC_STAT_AREA] >= min_area
    ]
    changed_ratio = float(np.count_nonzero(mask)) / max(1, int(np.count_nonzero(valid)))
    regions = tuple(
        (int(x / sc), int(y / sc), int(w / sc), int(h / sc))
        for x, y, w, h in regions_small
    )

    heat = cv2.applyColorMap(
        cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX), cv2.COLORMAP_JET
    )
    vis = cv2.addWeighted(cur, 0.55, heat, 0.45, 0)
    draw_rects(vis, regions_small, RED)
    ev = banner(
        vis,
        [
            f"compare_previous  {method.upper()} matches={matches} inliers={inliers}",
            f"changed_ratio={changed_ratio:.3f}  changed_regions={len(regions)}",
        ],
    )
    # H maps prev(small) -> curr(small). Lift it to original coordinates.
    S_c = np.diag([sc, sc, 1.0])
    S_p = np.diag([sp, sp, 1.0])
    H_full = np.linalg.inv(S_c) @ H @ S_p
    return CompareResult(
        ev, True, method, matches, inliers, changed_ratio, regions, H_full
    )
