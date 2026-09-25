"""zoom_recount: crop the uncertain regions, upscale them and re-detect.

For each region, the crop (plus 50% context) is upscaled with
``cv2.resize(INTER_CUBIC)`` and passed to the detector again. Detections
whose centre falls inside the region replace the earlier ones there. A
region is *resolved* when the zoomed pass is confident (every box ≥
``accept_conf``, or it finds no item and the earlier boxes were all weak).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from app.agent.tools.detect import UNCERTAIN, summarize
from app.agent.tools.draw import ORANGE, banner, draw_dets, mosaic
from app.agent.tools.types import Rect, ToolResultBase, center_in, clip_rect
from app.services.detector_cv import Det, Detector


@dataclass(frozen=True)
class RegionRecount:
    rect: Rect
    before: int
    after: int
    min_conf_after: float
    resolved: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "rect": list(self.rect),
            "before": self.before,
            "after": self.after,
            "min_conf_after": round(self.min_conf_after, 4),
            "resolved": self.resolved,
        }


@dataclass(frozen=True)
class ZoomResult(ToolResultBase):
    dets: tuple[Det, ...]
    count: int
    count_before: int
    regions: tuple[RegionRecount, ...]
    unresolved: tuple[Rect, ...]
    mean_conf: float
    uncertain_idx: tuple[int, ...]

    def outputs(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "count_before": self.count_before,
            "delta": self.count - self.count_before,
            "regions": [r.as_dict() for r in self.regions],
            "unresolved": len(self.unresolved),
            "uncertain": len(self.uncertain_idx),
            "boxes": [d.as_dict() for d in self.dets],
        }


def regions_from_dets(
    dets: tuple[Det, ...] | list[Det],
    idx: tuple[int, ...],
    shape: tuple[int, int],
    pad: float = 1.0,
) -> list[Rect]:
    """Square regions around the given detections (padded by ``pad`` × size)."""
    h, w = shape
    out: list[Rect] = []
    for i in idx:
        d = dets[i]
        side = max(d.w, d.h) * (1 + 2 * pad)
        cx, cy = d.x + d.w / 2, d.y + d.h / 2
        out.append(
            clip_rect(
                (int(cx - side / 2), int(cy - side / 2), int(side), int(side)), w, h
            )
        )
    return out


def zoom_recount(
    image: np.ndarray,
    detector: Detector,
    regions: list[Rect],
    base_dets: tuple[Det, ...] | list[Det],
    *,
    zoom: float = 2.0,
    accept_conf: float = 0.5,
    context: float = 0.5,
) -> ZoomResult:
    h, w = image.shape[:2]
    dets = list(base_dets)
    records: list[RegionRecount] = []
    crops: list[np.ndarray] = []
    for rect in regions:
        rx, ry, rw, rh = rect
        cx0 = rx - int(rw * context)
        cy0 = ry - int(rh * context)
        crect = clip_rect(
            (cx0, cy0, int(rw * (1 + 2 * context)), int(rh * (1 + 2 * context))), w, h
        )
        x, y, cw, ch = crect
        if cw < 4 or ch < 4:
            continue
        crop = image[y : y + ch, x : x + cw]
        big = cv2.resize(crop, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_CUBIC)
        zd = [
            Det(x + d.x / zoom, y + d.y / zoom, d.w / zoom, d.h / zoom, d.conf)
            for d in detector.detect(big)
        ]
        inside_new = [d for d in zd if center_in((d.x, d.y, d.w, d.h), rect)]
        inside_old = [d for d in dets if center_in((d.x, d.y, d.w, d.h), rect)]
        min_conf = min((d.conf for d in inside_new), default=1.0)
        old_all_weak = all(d.conf < UNCERTAIN[1] for d in inside_old)
        resolved = (bool(inside_new) and min_conf >= accept_conf) or (
            not inside_new and old_all_weak
        )
        if resolved:
            dets = [
                d for d in dets if not center_in((d.x, d.y, d.w, d.h), rect)
            ] + inside_new
        records.append(
            RegionRecount(
                rect, len(inside_old), len(inside_new), float(min_conf), resolved
            )
        )
        vis = big.copy()
        draw_dets(
            vis,
            [
                Det((d.x - x) * zoom, (d.y - y) * zoom, d.w * zoom, d.h * zoom, d.conf)
                for d in inside_new
            ],
        )
        rr = ((rx - x) * zoom, (ry - y) * zoom, rw * zoom, rh * zoom)
        cv2.rectangle(
            vis,
            (int(rr[0]), int(rr[1])),
            (int(rr[0] + rr[2]), int(rr[1] + rr[3])),
            ORANGE,
            2,
        )
        crops.append(vis)

    mean_conf, unc, _, _ = summarize(dets, (h, w))
    unresolved = tuple(r.rect for r in records if not r.resolved)
    lines = [
        f"zoom_recount  regions={len(records)}  zoom={zoom:.1f}x  "
        f"count {len(base_dets)} -> {len(dets)}  unresolved={len(unresolved)}"
    ]
    return ZoomResult(
        evidence=banner(mosaic(crops), lines),
        dets=tuple(dets),
        count=len(dets),
        count_before=len(base_dets),
        regions=tuple(records),
        unresolved=unresolved,
        mean_conf=mean_conf,
        uncertain_idx=unc,
    )
