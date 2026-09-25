"""detect: single-shot detection with the OpenCV 5 DNN detector, plus crowding stats."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.agent.tools.draw import banner, draw_dets, fit
from app.agent.tools.types import ToolResultBase
from app.services.detector_cv import Det, Detector

UNCERTAIN = (0.25, 0.5)


@dataclass(frozen=True)
class DetectResult(ToolResultBase):
    dets: tuple[Det, ...]
    count: int
    mean_conf: float
    uncertain_idx: tuple[int, ...]
    median_box_frac: float  # median box area / image area
    crowding: float  # share of items whose nearest neighbour is closer than 1 item size
    detector: str

    def outputs(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "mean_conf": round(self.mean_conf, 4),
            "uncertain": len(self.uncertain_idx),
            "median_box_frac": round(self.median_box_frac, 6),
            "crowding": round(self.crowding, 4),
            "detector": self.detector,
            "boxes": [d.as_dict() for d in self.dets],
        }


def crowd_stats(
    dets: list[Det] | tuple[Det, ...], shape: tuple[int, int]
) -> tuple[float, float]:
    if not dets:
        return 0.0, 0.0
    area = float(shape[0] * shape[1])
    areas = np.array([d.w * d.h for d in dets], np.float64)
    median_frac = float(np.median(areas) / area)
    if len(dets) < 2:
        return median_frac, 0.0
    c = np.array([[d.x + d.w / 2, d.y + d.h / 2] for d in dets], np.float64)
    size = np.sqrt(areas)
    dist = np.sqrt(((c[:, None, :] - c[None, :, :]) ** 2).sum(-1))
    np.fill_diagonal(dist, np.inf)
    crowded = dist.min(axis=1) < 1.0 * size
    return median_frac, float(crowded.mean())


def summarize(
    dets: list[Det], shape: tuple[int, int], uncertain: tuple[float, float] = UNCERTAIN
) -> tuple[float, tuple[int, ...], float, float]:
    mean_conf = float(np.mean([d.conf for d in dets])) if dets else 0.0
    unc = tuple(i for i, d in enumerate(dets) if uncertain[0] <= d.conf < uncertain[1])
    median_frac, crowding = crowd_stats(dets, shape)
    return mean_conf, unc, median_frac, crowding


def detect(
    image: np.ndarray, detector: Detector, title: str = "detect"
) -> DetectResult:
    dets = detector.detect(image)
    mean_conf, unc, median_frac, crowding = summarize(dets, image.shape[:2])
    vis, s = fit(image)
    draw_dets(vis, dets, s, UNCERTAIN)
    evidence = banner(
        vis,
        [
            f"{title}  count={len(dets)}  mean_conf={mean_conf:.2f}  uncertain={len(unc)}",
            f"detector={detector.name}  median_box={median_frac:.5f}  crowding={crowding:.2f}",
        ],
    )
    return DetectResult(
        evidence=evidence,
        dets=tuple(dets),
        count=len(dets),
        mean_conf=mean_conf,
        uncertain_idx=unc,
        median_box_frac=median_frac,
        crowding=crowding,
        detector=detector.name,
    )
