"""Typed I/O shared by the agent tools.

Every tool is a pure function: numpy images and plain parameters in, a frozen
result dataclass out. A result carries:

* ``outputs()``: the JSON-safe numbers written to the trace;
* ``evidence``: an image that the runner stores in S3/MinIO (tools never do I/O).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

Rect = tuple[int, int, int, int]  # x, y, w, h in the working-image frame


def rect_iou(a: Rect, b: Rect) -> float:
    ax1, ay1 = a[0] + a[2], a[1] + a[3]
    bx1, by1 = b[0] + b[2], b[1] + b[3]
    iw = max(0, min(ax1, bx1) - max(a[0], b[0]))
    ih = max(0, min(ay1, by1) - max(a[1], b[1]))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def center_in(det_xywh: tuple[float, float, float, float], r: Rect) -> bool:
    cx = det_xywh[0] + det_xywh[2] / 2
    cy = det_xywh[1] + det_xywh[3] / 2
    return r[0] <= cx < r[0] + r[2] and r[1] <= cy < r[1] + r[3]


def clip_rect(r: Rect, w: int, h: int) -> Rect:
    x0, y0 = max(0, int(r[0])), max(0, int(r[1]))
    x1, y1 = min(w, int(r[0] + r[2])), min(h, int(r[1] + r[3]))
    return (x0, y0, max(0, x1 - x0), max(0, y1 - y0))


@dataclass(frozen=True)
class ToolResultBase:
    evidence: np.ndarray | None

    def outputs(self) -> dict[str, Any]:  # pragma: no cover - overridden
        raise NotImplementedError
