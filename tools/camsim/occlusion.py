"""Occlusion-severity proxy (plan section F.6, output 4).

Samples formation-realistic player placements, projects every player into
each camera, and counts image-space overlaps where a nearer player covers a
farther one. Reported per pitch zone as the probability that a player at
that location is significantly occluded. Deterministic under a fixed seed.

The placement sampler is a stand-in until real trajectory data (e.g.
SoccerTrack v2) is plugged in via `positions_iter`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from tools.camsim.model import CameraSpec, PitchSpec

PLAYER_HEIGHT_M = 1.8
PLAYER_HALF_WIDTH_M = 0.25


@dataclass
class OcclusionConfig:
    n_samples: int = 200
    seed: int = 7
    overlap_iou: float = 0.3  # bbox IoU above which we call it occluded
    set_piece: bool = False  # cluster players in a penalty box instead


def sample_positions(
    pitch: PitchSpec, rng: np.random.Generator, set_piece: bool
) -> np.ndarray:
    """One placement of 22 players → (22, 3) ground points."""
    if set_piece:
        # Corner/penalty-box congestion: 16 players packed in one box,
        # 6 elsewhere.
        box_cx = pitch.length_m / 2 - 8.0
        packed = np.stack(
            [
                rng.uniform(box_cx - 8, box_cx + 8, 16),
                rng.uniform(-12, 12, 16),
                np.zeros(16),
            ],
            axis=1,
        )
        rest = np.stack(
            [
                rng.uniform(-pitch.length_m / 2 + 5, box_cx - 15, 6),
                rng.uniform(-pitch.width_m / 2 + 2, pitch.width_m / 2 - 2, 6),
                np.zeros(6),
            ],
            axis=1,
        )
        return np.concatenate([packed, rest])

    # Open play: two 4-4-2-ish grids around a shared "ball zone" focus.
    focus_x = rng.uniform(-pitch.length_m / 4, pitch.length_m / 4)
    focus_y = rng.uniform(-pitch.width_m / 4, pitch.width_m / 4)
    players = []
    for side in (-1.0, 1.0):
        lines_x = side * np.array([44.0, 28.0, 12.0, 2.0])
        counts = [1, 4, 4, 2]
        for lx, n in zip(lines_x, counts, strict=True):
            ys = np.linspace(-22, 22, n) if n > 1 else np.array([0.0])
            for ly in ys:
                # Compress toward the play focus + positional jitter.
                px = 0.65 * lx + 0.35 * focus_x + rng.normal(0, 3.0)
                py = 0.65 * ly + 0.35 * focus_y + rng.normal(0, 3.0)
                players.append([px, py, 0.0])
    pts = np.array(players)
    pts[:, 0] = np.clip(pts[:, 0], -pitch.length_m / 2 + 1, pitch.length_m / 2 - 1)
    pts[:, 1] = np.clip(pts[:, 1], -pitch.width_m / 2 + 1, pitch.width_m / 2 - 1)
    return pts


def _player_bboxes(cam: CameraSpec, positions: np.ndarray) -> np.ndarray:
    """Project players to image bboxes (N,4) xyxy; NaN rows if invisible."""
    feet, v0 = cam.project(positions)
    head, v1 = cam.project(positions + np.array([0, 0, PLAYER_HEIGHT_M]))
    left, _ = cam.project(positions + np.array([PLAYER_HALF_WIDTH_M, 0, 0]))
    half_w = np.abs(left[:, 0] - feet[:, 0])
    half_w = np.maximum(half_w, 1.0)
    visible = v0 & v1
    boxes = np.stack(
        [
            feet[:, 0] - half_w,
            np.minimum(head[:, 1], feet[:, 1]),
            feet[:, 0] + half_w,
            np.maximum(head[:, 1], feet[:, 1]),
        ],
        axis=1,
    )
    boxes[~visible] = np.nan
    return boxes


def _pair_iou(boxes: np.ndarray) -> np.ndarray:
    a = boxes[:, None, :]
    b = boxes[None, :, :]
    x1 = np.maximum(a[..., 0], b[..., 0])
    y1 = np.maximum(a[..., 1], b[..., 1])
    x2 = np.minimum(a[..., 2], b[..., 2])
    y2 = np.minimum(a[..., 3], b[..., 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area = (a[..., 2] - a[..., 0]) * (a[..., 3] - a[..., 1])
    union = area + area.swapaxes(0, 1) - inter
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(union > 0, inter / union, 0.0)


def occlusion_events(
    cam: CameraSpec, positions: np.ndarray, overlap_iou: float
) -> tuple[np.ndarray, np.ndarray]:
    """(occluded, visible) booleans (N,) for this camera.

    Player i is occluded when any nearer visible player j overlaps it above
    `overlap_iou`. Invisible players (outside FOV) are excluded from both —
    occlusion rates are conditioned on visibility; FOV coverage is a separate
    field.
    """
    boxes = _player_bboxes(cam, positions)
    visible = ~np.isnan(boxes).any(axis=1)
    dist = cam.distance_m(positions)
    iou = _pair_iou(boxes)
    np.fill_diagonal(iou, 0.0)
    with np.errstate(invalid="ignore"):
        overlapping = iou >= overlap_iou
    overlapping &= visible[None, :]  # only visible players can occlude
    nearer = dist[None, :] < dist[:, None]  # j nearer than i
    occluded = np.any(overlapping & nearer, axis=1) & visible
    return occluded, visible


def occlusion_rate_by_zone(
    cam: CameraSpec,
    pitch: PitchSpec,
    cfg: OcclusionConfig,
    zone_edges_x: np.ndarray,
    zone_edges_y: np.ndarray,
) -> tuple[np.ndarray, float]:
    """(zones_y, zones_x) occlusion probability grid + overall rate."""
    rng = np.random.default_rng(cfg.seed)
    hits = np.zeros((len(zone_edges_y) - 1, len(zone_edges_x) - 1))
    totals = np.zeros_like(hits)
    n_occ = 0
    n_all = 0
    for _ in range(cfg.n_samples):
        pos = sample_positions(pitch, rng, cfg.set_piece)
        occ, visible = occlusion_events(cam, pos, cfg.overlap_iou)
        xi = np.clip(
            np.digitize(pos[:, 0], zone_edges_x) - 1, 0, hits.shape[1] - 1
        )
        yi = np.clip(
            np.digitize(pos[:, 1], zone_edges_y) - 1, 0, hits.shape[0] - 1
        )
        np.add.at(totals, (yi, xi), visible.astype(float))
        np.add.at(hits, (yi, xi), occ.astype(float))
        n_occ += int(occ.sum())
        n_all += int(visible.sum())
    with np.errstate(invalid="ignore", divide="ignore"):
        grid = np.where(totals > 0, hits / totals, np.nan)
    overall = n_occ / n_all if n_all else 0.0
    return grid, overall
