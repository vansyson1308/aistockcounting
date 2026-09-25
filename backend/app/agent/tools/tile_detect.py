"""tile_detect: overlapping tiles, per-tile detection, global NMS merge.

Dense trays of small items defeat a single full-frame pass because each item
covers only a few pixels at the network input size. Tiling runs the same
OpenCV 5 DNN detector on overlapping crops (each crop is letterboxed up to
the network input), maps the boxes back and merges them:
1. drop boxes cut by an inner tile edge when a neighbour tile covers that edge;
2. ``cv2.dnn.NMSBoxes`` (IoU) across all tiles;
3. containment suppression (a box mostly inside a higher-scoring box).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from app.agent.tools.detect import UNCERTAIN, summarize
from app.agent.tools.draw import CYAN, banner, draw_dets, fit, label
from app.agent.tools.types import Rect, ToolResultBase, center_in
from app.services.detector_cv import Det, Detector, nms


@dataclass(frozen=True)
class TileResult(ToolResultBase):
    dets: tuple[Det, ...]
    count: int
    mean_conf: float
    uncertain_idx: tuple[int, ...]
    tiles: tuple[Rect, ...]
    tile_counts: tuple[int, ...]
    disagreement: tuple[
        Rect, ...
    ]  # tile cores where single-shot and tiled counts differ
    grid: tuple[int, int]

    def outputs(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "mean_conf": round(self.mean_conf, 4),
            "uncertain": len(self.uncertain_idx),
            "grid": list(self.grid),
            "tile_counts": list(self.tile_counts),
            "disagreement_cells": [list(r) for r in self.disagreement],
            "boxes": [d.as_dict() for d in self.dets],
        }


def choose_grid(
    shape: tuple[int, int], median_box_frac: float, n_single: int
) -> tuple[int, int]:
    """Pick a grid so that a typical item spans at least ~1.5% of a tile."""
    h, w = shape
    target = 0.015
    k = (
        2
        if median_box_frac <= 0
        else int(np.ceil(np.sqrt(target / max(median_box_frac, 1e-6))))
    )
    k = int(np.clip(k, 2, 4))
    if n_single > 150:
        k = max(k, 3)
    rows = k if h >= w else max(2, round(k * h / w))
    cols = k if w > h else max(2, round(k * w / h))
    return int(rows), int(cols)


def make_tiles(
    shape: tuple[int, int], grid: tuple[int, int], overlap: float
) -> list[Rect]:
    h, w = shape
    rows, cols = grid
    th, tw = h / rows, w / cols
    oy, ox = th * overlap, tw * overlap
    tiles: list[Rect] = []
    for r in range(rows):
        for c in range(cols):
            x0 = int(max(0, c * tw - ox))
            y0 = int(max(0, r * th - oy))
            x1 = int(min(w, (c + 1) * tw + ox))
            y1 = int(min(h, (r + 1) * th + oy))
            tiles.append((x0, y0, x1 - x0, y1 - y0))
    return tiles


def core_cells(shape: tuple[int, int], grid: tuple[int, int]) -> list[Rect]:
    h, w = shape
    rows, cols = grid
    return [
        (int(c * w / cols), int(r * h / rows), int(w / cols), int(h / rows))
        for r in range(rows)
        for c in range(cols)
    ]


def _containment_suppress(dets: list[Det], thr: float = 0.7) -> list[Det]:
    keep: list[Det] = []
    for d in sorted(dets, key=lambda x: -x.conf):
        inside = False
        for k in keep:
            ix = max(0.0, min(d.x + d.w, k.x + k.w) - max(d.x, k.x))
            iy = max(0.0, min(d.y + d.h, k.y + k.h) - max(d.y, k.y))
            if ix * iy >= thr * min(d.w * d.h, k.w * k.h):
                inside = True
                break
        if not inside:
            keep.append(d)
    return keep


def merge_tile_dets(
    per_tile: list[tuple[Rect, list[Det]]], shape: tuple[int, int], iou: float = 0.5
) -> list[Det]:
    h, w = shape
    merged: list[Det] = []
    edge = 2.0
    for (tx, ty, tw, th), dets in per_tile:
        for d in dets:
            gx, gy = d.x + tx, d.y + ty
            # A box touching an inner tile edge is probably truncated. The
            # neighbouring tile (which overlaps) sees the whole item.
            if (d.x <= edge and tx > 0) or (d.y <= edge and ty > 0):
                continue
            if (d.x + d.w >= tw - edge and tx + tw < w) or (
                d.y + d.h >= th - edge and ty + th < h
            ):
                continue
            merged.append(Det(gx, gy, d.w, d.h, d.conf))
    merged = nms(merged, 0.0, iou)
    return _containment_suppress(merged)


def tile_detect(
    image: np.ndarray,
    detector: Detector,
    *,
    grid: tuple[int, int] | None = None,
    overlap: float = 0.2,
    single_shot: list[Det] | tuple[Det, ...] = (),
    median_box_frac: float = 0.0,
) -> TileResult:
    shape = image.shape[:2]
    grid = grid or choose_grid(shape, median_box_frac, len(single_shot))
    tiles = make_tiles(shape, grid, overlap)
    per_tile = []
    for tx, ty, tw, th in tiles:
        crop = image[ty : ty + th, tx : tx + tw]
        per_tile.append(((tx, ty, tw, th), detector.detect(crop)))
    dets = merge_tile_dets(per_tile, shape)
    mean_conf, unc, _, _ = summarize(dets, shape)

    cells = core_cells(shape, grid)
    tile_counts, disagreement = [], []
    for cell in cells:
        n_tiled = sum(center_in((d.x, d.y, d.w, d.h), cell) for d in dets)
        n_single = sum(center_in((d.x, d.y, d.w, d.h), cell) for d in single_shot)
        tile_counts.append(int(n_tiled))
        if single_shot and n_tiled != n_single:
            disagreement.append(cell)

    vis, s = fit(image)
    for cell, n in zip(cells, tile_counts, strict=True):
        x, y, cw, ch = (int(v * s) for v in cell)
        color = (0, 0, 255) if cell in disagreement else CYAN
        cv2.rectangle(vis, (x, y), (x + cw, y + ch), color, 2)
        label(vis, f"{n}", (x + 6, y + 24))
    draw_dets(vis, dets, s, UNCERTAIN)
    evidence = banner(
        vis,
        [
            f"tile_detect  grid={grid[0]}x{grid[1]}  overlap={overlap:.0%}  count={len(dets)}"
            f"  (single-shot {len(single_shot)})",
            f"cells where tiled != single-shot: {len(disagreement)}",
        ],
    )
    return TileResult(
        evidence=evidence,
        dets=tuple(dets),
        count=len(dets),
        mean_conf=mean_conf,
        uncertain_idx=unc,
        tiles=tuple(tiles),
        tile_counts=tuple(tile_counts),
        disagreement=tuple(disagreement),
        grid=grid,
    )
