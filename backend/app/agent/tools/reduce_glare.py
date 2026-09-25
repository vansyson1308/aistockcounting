"""reduce_glare: inpaint specular highlights and even out local contrast.

The HSV highlight mask is dilated and filled with ``cv2.inpaint`` (Telea).
CLAHE is then applied to the L channel in LAB. Inpainting cannot recover an
item that is fully hidden under glare, so the controller treats the result as
*degraded* evidence and never auto-accepts after heavy glare.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from app.agent.tools.draw import banner, side_by_side
from app.agent.tools.types import ToolResultBase
from app.utils.image_quality import glare_mask

WORK_SIDE = 1600


@dataclass(frozen=True)
class GlareResult(ToolResultBase):
    image: np.ndarray
    glare_before: float
    glare_after: float
    inpainted_frac: float

    def outputs(self) -> dict[str, Any]:
        return {
            "glare_before": round(self.glare_before, 4),
            "glare_after": round(self.glare_after, 4),
            "inpainted_frac": round(self.inpainted_frac, 4),
        }


def _ratio(mask: np.ndarray) -> float:
    return float(np.count_nonzero(mask)) / mask.size


def reduce_glare(
    image: np.ndarray, radius: int = 5, clahe_clip: float = 2.0
) -> GlareResult:
    h, w = image.shape[:2]
    s = min(1.0, WORK_SIDE / max(h, w))
    work = (
        cv2.resize(image, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
        if s < 1
        else image.copy()
    )
    mask = glare_mask(work)
    before = _ratio(mask)
    mask_d = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    inpainted = (
        cv2.inpaint(work, mask_d, radius, cv2.INPAINT_TELEA) if before > 0 else work
    )
    lab = cv2.cvtColor(inpainted, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    l_ch = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8)).apply(l_ch)
    out = cv2.cvtColor(cv2.merge([l_ch, a_ch, b_ch]), cv2.COLOR_LAB2BGR)
    if s < 1:
        out = cv2.resize(out, (w, h), interpolation=cv2.INTER_CUBIC)
    after = _ratio(glare_mask(out))
    evidence = banner(
        side_by_side(image, out),
        [
            f"reduce_glare  glare {before:.3f} -> {after:.3f}  (inpaint TELEA r={radius} + CLAHE)"
        ],
    )
    return GlareResult(
        evidence=evidence,
        image=out,
        glare_before=before,
        glare_after=after,
        inpainted_frac=_ratio(mask_d),
    )
