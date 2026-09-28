"""GT-only, deterministic selection of the frozen diagnostic windows (§9.5).

Roles: TUNE (short, typical crowding — tracker margin selection only),
OPEN (lowest crowding at normal population), DENSE (highest sustained
overlap), FAR (smallest median GT bbox height). Windows are mutually
disjoint. No model output is consulted; the result is hashed and frozen.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import yaml

from ml.gate0a.runners.select_dense_windows import frame_crowding

ROLES = ("DENSE", "FAR", "OPEN", "TUNE")


def per_frame_stats(frames, crowd_iou: float) -> dict[int, dict]:
    stats = {}
    for f, dets in frames.items():
        pairs, crowd = frame_crowding(dets, crowd_iou)
        hs = np.array([b[3] - b[1] for _, b, _ in dets]) if dets else np.zeros(0)
        stats[f] = {
            "n": len(dets),
            "pairs": pairs,
            "crowd": crowd,
            "med_h": float(np.median(hs)) if hs.size else float("nan"),
            "heights": hs,
        }
    return stats


def _window_summary(stats: dict[int, dict], f0: int, f1: int) -> dict | None:
    fs = [f for f in range(f0, f1 + 1) if f in stats]
    if len(fs) < 0.95 * (f1 - f0 + 1):
        return None
    hs = np.concatenate([stats[f]["heights"] for f in fs]) if fs else np.zeros(0)
    if hs.size == 0:
        return None
    return {
        "start_frame": int(f0),
        "end_frame": int(f1),
        "n_frames": int(f1 - f0 + 1),
        "annotated_frames": len(fs),
        "mean_overlap_pairs": round(float(np.mean([stats[f]["pairs"] for f in fs])), 4),
        "peak_crowd_size": int(max(stats[f]["crowd"] for f in fs)),
        "median_bbox_h": round(float(np.median(hs)), 2),
        "p05_bbox_h": round(float(np.percentile(hs, 5)), 2),
        "mean_gt_boxes": round(float(np.mean([stats[f]["n"] for f in fs])), 3),
    }


def _disjoint(w: dict, chosen: list[dict]) -> bool:
    return all(w["end_frame"] < c["start_frame"] or w["start_frame"] > c["end_frame"] for c in chosen)


def select_windows(frames, fps: float, cfg: dict, frame_min: int | None = None,
                   frame_max: int | None = None) -> dict[str, dict]:
    stats = per_frame_stats(frames, float(cfg["crowd_iou"]))
    ids = sorted(frames)
    lo = max(ids[0], frame_min) if frame_min is not None else ids[0]
    hi = min(ids[-1], frame_max) if frame_max is not None else ids[-1]
    clip_len = round(float(cfg["clip_seconds"]) * fps)
    tune_len = round(float(cfg["tune_seconds"]) * fps)
    stride = max(1, round(float(cfg["candidate_stride_seconds"]) * fps))

    def candidates(length: int) -> list[dict]:
        out = []
        for f0 in range(lo, hi - length + 2, stride):
            s = _window_summary(stats, f0, f0 + length - 1)
            if s:
                out.append(s)
        return out

    cands = candidates(clip_len)
    if not cands:
        raise ValueError("no fully-annotated candidate window of the requested length")
    median_n = float(np.median([c["mean_gt_boxes"] for c in cands]))
    chosen: list[dict] = []
    out: dict[str, dict] = {}

    dense = max(cands, key=lambda c: (c["mean_overlap_pairs"], -c["start_frame"]))
    dense = {**dense, "role": "DENSE", "selection_statistic": "argmax mean_overlap_pairs"}
    chosen.append(dense)
    out["DENSE"] = dense

    far_pool = [c for c in cands if _disjoint(c, chosen)]
    far = min(far_pool, key=lambda c: (c["median_bbox_h"], c["start_frame"]))
    far = {**far, "role": "FAR", "selection_statistic": "argmin median_bbox_h (disjoint)"}
    chosen.append(far)
    out["FAR"] = far

    ratio = float(cfg["open_min_population_ratio"])
    open_pool = [c for c in cands if _disjoint(c, chosen) and c["mean_gt_boxes"] >= ratio * median_n]
    if not open_pool:
        open_pool = [c for c in cands if _disjoint(c, chosen)]
    open_w = min(open_pool, key=lambda c: (c["mean_overlap_pairs"], c["start_frame"]))
    open_w = {**open_w, "role": "OPEN",
              "selection_statistic": f"argmin mean_overlap_pairs with mean_gt_boxes >= {ratio}xmedian (disjoint)"}
    chosen.append(open_w)
    out["OPEN"] = open_w

    tune_c = [c for c in candidates(tune_len) if _disjoint(c, chosen)]
    if tune_c:
        med_pairs = float(np.median([c["mean_overlap_pairs"] for c in cands]))
        tune = min(tune_c, key=lambda c: (abs(c["mean_overlap_pairs"] - med_pairs), c["start_frame"]))
        out["TUNE"] = {**tune, "role": "TUNE",
                       "selection_statistic": "closest to median mean_overlap_pairs (disjoint, short)"}
    for w in out.values():
        w["start_s"] = round((w["start_frame"] - 1) / fps, 2)
        w["end_s"] = round(w["end_frame"] / fps, 2)
    return out


def freeze(windows: dict[str, dict], meta: dict, out_path: Path) -> str:
    doc = {
        "banner": "DIAGNOSTIC — NOT OFFICIAL GATE 0A VERDICT / TEST SET UNTOUCHED",
        "method": "GT-only deterministic selection (ml.gate0a.cloud.select_clips); "
                  "no model prediction existed when frozen",
        **meta,
        "windows": {k: windows[k] for k in ROLES if k in windows},
    }
    text = yaml.safe_dump(doc, sort_keys=False)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    return hashlib.sha256(text.encode()).hexdigest()


def load_frozen(path: Path) -> tuple[dict, str]:
    text = Path(path).read_text()
    return yaml.safe_load(text), hashlib.sha256(text.encode()).hexdigest()
