"""Offline global tracklet reconciliation seed (plan §I, GTA-style).

Two passes, reimplemented clean-room from the published idea (Global Tracklet
Association for MOT in sports, arXiv:2411.08216):

1. **Split** — detect identity mixtures inside a tracklet by clustering its
   detection embeddings (DBSCAN on cosine distance) and cutting the tracklet
   into temporally contiguous runs of the same cluster.
2. **Merge** — constrained agglomerative association of temporally disjoint
   tracklets: candidate pairs must satisfy a spatio-temporal reachability
   gate and team consistency; pairs are merged best-first by aggregated
   embedding cosine distance until no pair beats the threshold. Temporal
   overlap anywhere in a merged group is a hard conflict.

This is deliberately evidence-general: pitch-coordinate gating, jersey votes
and capacity constraints (plan section I, layers 2-3) slot into `_pair_feasible` /
`_pair_cost` as further evidence streams in later phases.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ml.associate.dbscan import dbscan_labels
from ml.associate.tracklets import Tracklet, overlaps


@dataclass
class ReconcileConfig:
    # Split pass
    split_eps: float = 0.35  # cosine-distance neighborhood for same identity
    split_min_samples: int = 5
    split_min_run: int = 5  # discard sub-runs shorter than this (noise)
    # Merge pass
    merge_max_cost: float = 0.35  # max cosine distance to merge
    max_gap_frames: int = 250  # ~10 s at 25 fps for the seed
    max_speed_px: float = 12.0  # reachability gate: px per frame
    reach_slack_px: float = 60.0
    require_team_match: bool = True


# ------------------------------------------------------------------- split


def split_tracklet(
    t: Tracklet, cfg: ReconcileConfig, next_id: int
) -> tuple[list[Tracklet], int]:
    """Split one tracklet into identity-consistent runs. Returns (parts, next_id)."""
    if t.embeddings is None or len(t.frames) < 2 * cfg.split_min_samples:
        return [t], next_id
    emb = t.embeddings
    dist = 1.0 - emb @ emb.T
    np.clip(dist, 0.0, 2.0, out=dist)
    labels = dbscan_labels(dist, eps=cfg.split_eps, min_samples=cfg.split_min_samples)
    clusters = set(labels[labels >= 0])
    if len(clusters) <= 1:
        return [t], next_id

    # Cut into temporally contiguous runs of a single cluster label; attach
    # noise points to the current run.
    parts: list[Tracklet] = []
    run_start = 0
    current = labels[0]
    for i in range(1, len(labels) + 1):
        boundary = i == len(labels) or (
            labels[i] >= 0 and current >= 0 and labels[i] != current
        )
        if boundary:
            mask = np.zeros(len(labels), dtype=bool)
            mask[run_start:i] = True
            if mask.sum() >= cfg.split_min_run:
                parts.append(t.slice(mask, next_id))
                next_id += 1
            run_start = i
        if i < len(labels) and labels[i] >= 0:
            current = labels[i]
    if not parts:  # everything was noise-short; keep the original
        return [t], next_id
    return parts, next_id


# ------------------------------------------------------------------- merge


def _pair_feasible(a: Tracklet, b: Tracklet, cfg: ReconcileConfig) -> bool:
    """a must end before b starts, within reachability and team consistency."""
    if a.end >= b.start:
        return False
    gap = b.start - a.end
    if gap > cfg.max_gap_frames:
        return False
    if (
        cfg.require_team_match
        and a.team is not None
        and b.team is not None
        and a.team != b.team
    ):
        return False
    travel = float(np.linalg.norm(b.center_at(0) - a.center_at(len(a.frames) - 1)))
    return travel <= cfg.max_speed_px * gap + cfg.reach_slack_px


def _pair_cost(a: Tracklet, b: Tracklet) -> float:
    ea, eb = a.mean_embedding(), b.mean_embedding()
    if ea is None or eb is None:
        return float("inf")
    return float(1.0 - np.dot(ea, eb))


def _group_conflict(group_a: list[Tracklet], group_b: list[Tracklet]) -> bool:
    return any(overlaps(x, y) for x in group_a for y in group_b)


def merge_tracklets(
    tracklets: list[Tracklet], cfg: ReconcileConfig
) -> list[list[Tracklet]]:
    """Best-first constrained agglomeration. Returns groups of tracklets."""
    groups: list[list[Tracklet]] = [[t] for t in tracklets]

    def group_cost(ga: list[Tracklet], gb: list[Tracklet]) -> float:
        # Order-agnostic: evaluate the temporal seam between the two groups.
        first, second = (ga, gb) if ga[-1].end < gb[0].start else (gb, ga)
        tail, head = first[-1], second[0]
        if not _pair_feasible(tail, head, cfg):
            return float("inf")
        return _pair_cost(tail, head)

    while True:
        best = (float("inf"), -1, -1)
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                if _group_conflict(groups[i], groups[j]):
                    continue
                c = group_cost(groups[i], groups[j])
                if c < best[0]:
                    best = (c, i, j)
        cost, i, j = best
        if cost > cfg.merge_max_cost:
            break
        merged = sorted(groups[i] + groups[j], key=lambda t: t.start)
        groups = [g for k, g in enumerate(groups) if k not in (i, j)]
        groups.append(merged)
    return groups


# --------------------------------------------------------------- entrypoint


def audit_pairs(parts: list[Tracklet], cfg: ReconcileConfig) -> dict[str, int]:
    """Classify every ordered tracklet pair once (pre-merge accounting).

    conflicts: temporally overlapping (can never be the same player);
    gate_rejected: disjoint but outside the reachability/gap/team gate;
    cost_rejected: feasible but appearance cost above `merge_max_cost`;
    feasible_under_cost: merge candidates before agglomeration.
    """
    counts = {"pairs": 0, "conflicts": 0, "gate_rejected": 0,
              "cost_rejected": 0, "feasible_under_cost": 0}
    ordered = sorted(parts, key=lambda t: t.start)
    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            a, b = ordered[i], ordered[j]
            counts["pairs"] += 1
            if overlaps(a, b):
                counts["conflicts"] += 1
            elif not _pair_feasible(a, b, cfg):
                counts["gate_rejected"] += 1
            elif _pair_cost(a, b) > cfg.merge_max_cost:
                counts["cost_rejected"] += 1
            else:
                counts["feasible_under_cost"] += 1
    return counts


def reconcile_with_stats(
    tracklets: list[Tracklet], cfg: ReconcileConfig | None = None
) -> tuple[dict[int, int], dict[str, int]]:
    """`reconcile` plus split/merge accounting (accepted merges, rejections)."""
    cfg = cfg or ReconcileConfig()
    parts: list[Tracklet] = []
    next_id = max((t.tracklet_id for t in tracklets), default=0) + 1
    n_split = 0
    for t in tracklets:
        split, next_id = split_tracklet(t, cfg, next_id)
        n_split += len(split) > 1
        parts.extend(split)
    stats = {"n_tracklets_in": len(tracklets), "n_tracklets_split": n_split,
             "n_parts_after_split": len(parts)}
    stats.update(audit_pairs(parts, cfg))
    groups = merge_tracklets(parts, cfg)
    stats["n_canonical_out"] = len(groups)
    stats["merges_accepted"] = len(parts) - len(groups)
    stats["merges_rejected"] = stats["gate_rejected"] + stats["cost_rejected"]
    mapping: dict[int, int] = {}
    for canonical, group in enumerate(
        sorted(groups, key=lambda g: g[0].start), start=1
    ):
        for t in group:
            mapping[t.tracklet_id] = canonical
    return mapping, stats


def reconcile(
    tracklets: list[Tracklet], cfg: ReconcileConfig | None = None
) -> dict[int, int]:
    """Full offline pass. Returns {original tracklet_id -> canonical id}.

    Canonical ids are assigned 1..K over the merged groups (split parts keep
    mapping back to the *original* tracklet id per frame range is handled by
    callers that re-emit rows; this seed maps whole tracklets).
    """
    mapping, _stats = reconcile_with_stats(tracklets, cfg)
    return mapping
