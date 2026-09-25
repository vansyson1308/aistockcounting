"""assess_quality: blur, glare, exposure and tray coverage (OpenCV 5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from app.agent.tools.draw import GREEN, RED, banner, fit
from app.agent.tools.types import ToolResultBase
from app.cv.imageio import resize_max_side
from app.utils.image_quality import WORK_SIDE, assess_image_quality, glare_mask


@dataclass(frozen=True)
class QualityResult(ToolResultBase):
    score: float
    flags: tuple[str, ...]
    metrics: dict[str, float]
    tray_quad: np.ndarray | None  # in input-image coords

    def outputs(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "flags": list(self.flags),
            **self.metrics,
            "tray_found": self.tray_quad is not None,
        }


def assess_quality(image: np.ndarray) -> QualityResult:
    from app.cv.tray import locate_tray

    q = assess_image_quality(image)
    tray = locate_tray(image)

    vis, s = fit(image)
    small, s_mask = resize_max_side(image, WORK_SIDE)
    gmask = glare_mask(small)
    gmask = cv2.resize(
        gmask, (vis.shape[1], vis.shape[0]), interpolation=cv2.INTER_NEAREST
    )
    red = np.zeros_like(vis)
    red[:] = RED
    vis = np.where(gmask[..., None] > 0, cv2.addWeighted(vis, 0.3, red, 0.7, 0), vis)
    if tray.quad is not None:
        cv2.polylines(vis, [(tray.quad * s).astype(np.int32)], True, GREEN, 3)
    m = q.metrics
    evidence = banner(
        vis,
        [
            f"assess_quality  score={q.score:.2f}  flags={','.join(q.flags) or 'none'}",
            f"blur_var={m['blur_var']:.0f}  glare={m['glare_ratio']:.3f}  "
            f"tray_cov={m['tray_coverage']:.2f}  p99={m['brightness_p99']:.0f}",
        ],
    )
    return QualityResult(
        evidence=evidence,
        score=q.score,
        flags=tuple(q.flags),
        metrics=dict(m),
        tray_quad=tray.quad,
    )
