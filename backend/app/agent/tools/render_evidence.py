"""render_evidence: the annotated review sheet a human approves from."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from app.agent.tools.draw import (
    CYAN,
    ORANGE,
    RED,
    banner,
    draw_dets,
    draw_rects,
    fit,
    side_by_side,
)
from app.agent.tools.types import Rect, ToolResultBase
from app.services.detector_cv import Det


@dataclass(frozen=True)
class EvidenceSheet(ToolResultBase):
    boxes: int
    uncertain_regions: int
    changed_regions: int

    def outputs(self) -> dict[str, Any]:
        return {
            "boxes": self.boxes,
            "uncertain_regions": self.uncertain_regions,
            "changed_regions": self.changed_regions,
        }


def render_evidence(
    image: np.ndarray,
    dets: tuple[Det, ...] | list[Det],
    *,
    headline: str,
    details: list[str],
    uncertain_regions: list[Rect] | tuple[Rect, ...] = (),
    changed_regions: list[Rect] | tuple[Rect, ...] = (),
    diff_heatmap: np.ndarray | None = None,
) -> EvidenceSheet:
    vis, s = fit(image, 1400)
    draw_dets(vis, dets, s)
    draw_rects(vis, uncertain_regions, ORANGE, s)
    draw_rects(vis, changed_regions, RED, s)
    for i, d in enumerate(dets):
        cv2.putText(
            vis,
            str(i + 1),
            (int(d.x * s), max(12, int(d.y * s) - 3)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            CYAN,
            1,
            cv2.LINE_AA,
        )
    body = (
        side_by_side(vis, diff_heatmap, height=vis.shape[0])
        if diff_heatmap is not None
        else vis
    )
    legend = (
        "green: counted  orange: uncertain  red: changed vs previous approved photo"
    )
    sheet = banner(body, [headline, *details[:4], legend])
    return EvidenceSheet(
        evidence=sheet,
        boxes=len(dets),
        uncertain_regions=len(uncertain_regions),
        changed_regions=len(changed_regions),
    )
