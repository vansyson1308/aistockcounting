"""rectify_tray: find the tray quadrilateral and warp it to a fronto-parallel view."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from app.agent.tools.draw import GREEN, banner, fit, side_by_side
from app.agent.tools.types import ToolResultBase
from app.cv.tray import FULL_FRAME_FRAC, locate_tray, order_quad

MAX_OUT_SIDE = 1600


@dataclass(frozen=True)
class RectifyResult(ToolResultBase):
    found: bool
    method: str
    quad: np.ndarray | None
    homography: np.ndarray  # 3x3, input -> rectified (identity when not found)
    image: np.ndarray  # rectified image (the input when not found)

    def outputs(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "method": self.method,
            "quad": None if self.quad is None else np.round(self.quad, 1).tolist(),
            "out_size": [int(self.image.shape[1]), int(self.image.shape[0])],
        }


def rectify_tray(image: np.ndarray, quad: np.ndarray | None = None) -> RectifyResult:
    method = "given"
    if quad is None:
        loc = locate_tray(image)
        quad, method = loc.quad, loc.method
        # A quad that is essentially the whole frame (a close-up) needs no warp.
        if quad is not None and loc.coverage >= FULL_FRAME_FRAC:
            quad = None
    if quad is None:
        vis, _ = fit(image)
        return RectifyResult(
            evidence=banner(
                vis, ["rectify_tray  no tray quad found: using the full frame"]
            ),
            found=False,
            method="none",
            quad=None,
            homography=np.eye(3),
            image=image,
        )

    q = order_quad(np.asarray(quad, np.float32))
    w_top = np.linalg.norm(q[1] - q[0])
    w_bot = np.linalg.norm(q[2] - q[3])
    h_l = np.linalg.norm(q[3] - q[0])
    h_r = np.linalg.norm(q[2] - q[1])
    out_w, out_h = max(w_top, w_bot), max(h_l, h_r)
    s = min(1.0, MAX_OUT_SIDE / max(out_w, out_h))
    out_w, out_h = max(8, int(out_w * s)), max(8, int(out_h * s))
    dst = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], np.float32
    )
    H = cv2.getPerspectiveTransform(q, dst)
    warped = cv2.warpPerspective(image, H, (out_w, out_h), flags=cv2.INTER_LINEAR)

    vis, vs = fit(image)
    cv2.polylines(vis, [(q * vs).astype(np.int32)], True, GREEN, 3)
    evidence = banner(
        side_by_side(vis, warped),
        [f"rectify_tray  method={method}  out={out_w}x{out_h}"],
    )
    return RectifyResult(
        evidence=evidence, found=True, method=method, quad=q, homography=H, image=warped
    )
