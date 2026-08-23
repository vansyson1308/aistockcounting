"""Tracking metrics: Identity (IDF1) + switch/coverage metrics.

Native implementations of the metrics the product SLAs are written in
(plan §R): IDF1 (trajectory-level identity F1, Ristani et al. 2016),
CLEAR-style ID switches, track completeness (player-minute coverage), and
**identity integrity** — the fraction of GT player-time attributed to that
player's majority predicted identity. HOTA comes from the official TrackEval
package via `ml.eval.trackeval_wrapper` (not reimplemented here on purpose).

Matching: per-frame Hungarian on IoU with a 0.5 threshold, as in CLEAR.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import pairwise

import numpy as np
from scipy.optimize import linear_sum_assignment

from ml.track.tracker import iou_matrix

FrameBoxes = dict[int, list[tuple[int, np.ndarray, float]]]


@dataclass
class TrackingMetrics:
    idf1: float
    idtp: int
    idfp: int
    idfn: int
    id_switches: int
    num_gt_boxes: int
    num_matched_boxes: int
    completeness: float  # matched GT boxes / GT boxes ("player-minute coverage")
    identity_integrity: float  # majority-pred-id share of *matched* GT time
    # (orthogonal to completeness: coverage is measured by `completeness`,
    #  identity consistency of the covered time by `identity_integrity`)
    per_gt_integrity: dict[int, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "idf1": round(self.idf1, 4),
            "idtp": self.idtp,
            "idfp": self.idfp,
            "idfn": self.idfn,
            "id_switches": self.id_switches,
            "num_gt_boxes": self.num_gt_boxes,
            "completeness": round(self.completeness, 4),
            "identity_integrity": round(self.identity_integrity, 4),
        }


def _frame_matches(
    gt: FrameBoxes, pred: FrameBoxes, iou_thresh: float
) -> list[tuple[int, int, int]]:
    """Per-frame Hungarian matching → list of (frame, gt_id, pred_id)."""
    matches = []
    for frame in sorted(set(gt) | set(pred)):
        g = gt.get(frame, [])
        p = pred.get(frame, [])
        if not g or not p:
            continue
        gboxes = np.stack([b for _, b, _ in g])
        pboxes = np.stack([b for _, b, _ in p])
        iou = iou_matrix(gboxes, pboxes)
        cost = 1.0 - iou
        cost[iou < iou_thresh] = 1e6
        rows, cols = linear_sum_assignment(cost)
        for r, c in zip(rows, cols, strict=True):
            if cost[r, c] < 1e6:
                matches.append((frame, g[r][0], p[c][0]))
    return matches


def evaluate_tracking(
    gt: FrameBoxes, pred: FrameBoxes, iou_thresh: float = 0.5
) -> TrackingMetrics:
    matches = _frame_matches(gt, pred, iou_thresh)

    num_gt = sum(len(v) for v in gt.values())
    num_pred = sum(len(v) for v in pred.values())

    # --- Identity metrics (IDF1): global bipartite GT-id <-> pred-id.
    overlap: dict[tuple[int, int], int] = defaultdict(int)
    for _, gid, pid in matches:
        overlap[(gid, pid)] += 1
    gt_ids = sorted({gid for f in gt.values() for gid, _, _ in f})
    pred_ids = sorted({pid for f in pred.values() for pid, _, _ in f})
    gt_index = {g: i for i, g in enumerate(gt_ids)}
    pred_index = {p: i for i, p in enumerate(pred_ids)}
    counts = np.zeros((len(gt_ids), len(pred_ids)))
    for (gid, pid), n in overlap.items():
        counts[gt_index[gid], pred_index[pid]] = n
    idtp = 0
    if counts.size:
        rows, cols = linear_sum_assignment(-counts)
        idtp = int(counts[rows, cols].sum())
    idfn = num_gt - idtp
    idfp = num_pred - idtp
    idf1 = (2 * idtp / (2 * idtp + idfp + idfn)) if (idtp + idfp + idfn) else 0.0

    # --- ID switches (CLEAR-style): per GT id, changes in matched pred id.
    per_gt_sequence: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for frame, gid, pid in matches:
        per_gt_sequence[gid].append((frame, pid))
    id_switches = 0
    for seq in per_gt_sequence.values():
        seq.sort()
        for (_, prev), (_, cur) in pairwise(seq):
            if prev != cur:
                id_switches += 1

    # --- Coverage & identity integrity.
    matched_per_gt: dict[int, int] = defaultdict(int)
    majority_per_gt: dict[int, int] = {}
    for gid, seq in per_gt_sequence.items():
        matched_per_gt[gid] = len(seq)
        pid_counts: dict[int, int] = defaultdict(int)
        for _, pid in seq:
            pid_counts[pid] += 1
        majority_per_gt[gid] = max(pid_counts.values())
    gt_boxes_per_id: dict[int, int] = defaultdict(int)
    for frame_dets in gt.values():
        for gid, _, _ in frame_dets:
            gt_boxes_per_id[gid] += 1
    completeness = (sum(matched_per_gt.values()) / num_gt) if num_gt else 0.0
    per_gt_integrity = {
        gid: (majority_per_gt.get(gid, 0) / matched_per_gt[gid])
        if matched_per_gt.get(gid)
        else 0.0
        for gid in gt_boxes_per_id
    }
    total_matched = sum(matched_per_gt.values())
    identity_integrity = (
        sum(majority_per_gt.values()) / total_matched if total_matched else 0.0
    )

    return TrackingMetrics(
        idf1=idf1,
        idtp=idtp,
        idfp=idfp,
        idfn=idfn,
        id_switches=id_switches,
        num_gt_boxes=num_gt,
        num_matched_boxes=sum(matched_per_gt.values()),
        completeness=completeness,
        identity_integrity=identity_integrity,
        per_gt_integrity=per_gt_integrity,
    )
