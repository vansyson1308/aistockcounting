"""Optional wrapper around the official TrackEval package (MIT) for HOTA.

HOTA/DetA/AssA are deliberately NOT reimplemented here — subtle metric bugs
would silently corrupt every gate decision. When `trackeval` is installed
(ml/requirements-dev.txt), `hota_from_frames` computes HOTA-family scores for
one sequence directly from in-memory frame dicts; otherwise it raises
`TrackEvalUnavailable` with install instructions, and callers surface that
clearly instead of skipping silently.
"""

from __future__ import annotations

import numpy as np

from ml.eval.metrics import FrameBoxes
from ml.track.tracker import iou_matrix


class TrackEvalUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "trackeval is not installed. Install the official package: "
            "pip install 'git+https://github.com/JonathonLuiten/TrackEval.git'"
        )


def hota_from_frames(gt: FrameBoxes, pred: FrameBoxes) -> dict[str, float]:
    """Compute HOTA/DetA/AssA (+LocA) for one sequence via TrackEval."""
    # Upstream TrackEval still references numpy scalar aliases removed in
    # numpy >= 1.24 (np.float / np.int / np.bool). Restore them defensively
    # before importing; no-op where already defined.
    for _alias, _type in (("float", float), ("int", int), ("bool", bool)):
        if not hasattr(np, _alias):
            setattr(np, _alias, _type)

    try:
        from trackeval.metrics import HOTA
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise TrackEvalUnavailable() from exc

    frames = sorted(set(gt) | set(pred))
    gt_ids_sorted = sorted({gid for f in gt.values() for gid, _, _ in f})
    pr_ids_sorted = sorted({pid for f in pred.values() for pid, _, _ in f})
    gt_map = {g: i for i, g in enumerate(gt_ids_sorted)}
    pr_map = {p: i for i, p in enumerate(pr_ids_sorted)}

    data: dict = {
        "num_timesteps": len(frames),
        "num_gt_ids": len(gt_ids_sorted),
        "num_tracker_ids": len(pr_ids_sorted),
        "num_gt_dets": sum(len(v) for v in gt.values()),
        "num_tracker_dets": sum(len(v) for v in pred.values()),
        "gt_ids": [],
        "tracker_ids": [],
        "similarity_scores": [],
    }
    for frame in frames:
        g = gt.get(frame, [])
        p = pred.get(frame, [])
        data["gt_ids"].append(np.array([gt_map[gid] for gid, _, _ in g], dtype=int))
        data["tracker_ids"].append(
            np.array([pr_map[pid] for pid, _, _ in p], dtype=int)
        )
        if g and p:
            sim = iou_matrix(
                np.stack([b for _, b, _ in g]), np.stack([b for _, b, _ in p])
            )
        else:
            sim = np.zeros((len(g), len(p)))
        data["similarity_scores"].append(sim)

    metric = HOTA()
    res = metric.eval_sequence(data)
    return {
        "hota": float(np.mean(res["HOTA"])),
        "deta": float(np.mean(res["DetA"])),
        "assa": float(np.mean(res["AssA"])),
        "loca": float(np.mean(res["LocA"])),
    }
