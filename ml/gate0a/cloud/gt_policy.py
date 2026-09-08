"""Ground-truth handling policy for the diagnostic run.

* MOTChallenge `conf == 0` rows are ignore regions (SoccerTrack v2
  format-mot.md): excluded from GT and used to suppress overlapping
  predictions before scoring.
* GSR role/team attributes are linked to MOT ids by box overlap and used for
  SCORING ONLY (team accuracy, ReID diagnostics, O4 upper bound).
* GT is restricted to the frame domain actually present in the decoded video.
"""

from __future__ import annotations

import configparser
import contextlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ml.track.tracker import iou_matrix

Frames = dict[int, list[tuple[int, np.ndarray, float]]]


def parse_seqinfo(text: str) -> dict:
    cp = configparser.ConfigParser()
    cp.read_string(text)
    if "Sequence" not in cp:
        return {}
    s = cp["Sequence"]
    out: dict = {"name": s.get("name")}
    for key, cast in (("frameRate", float), ("seqLength", int), ("imWidth", int), ("imHeight", int)):
        if key in s:
            try:
                out[key] = cast(s[key])
            except ValueError:
                out[key] = s[key]
    return out


def load_gt(gt_path: Path | str, drop_ignore: bool = True) -> tuple[Frames, Frames, dict]:
    """Return (consider_frames, ignore_frames, stats) from a MOT gt.txt."""
    consider: Frames = defaultdict(list)
    ignore: Frames = defaultdict(list)
    n_rows = n_ignore = n_invalid = 0
    classes: Counter = Counter()
    heights: list[float] = []
    vis: list[float] = []
    ids: set[int] = set()
    for raw in Path(gt_path).read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        p = line.split(",")
        if len(p) < 6:
            n_invalid += 1
            continue
        frame, tid = int(float(p[0])), int(float(p[1]))
        x, y, w, h = (float(v) for v in p[2:6])
        if w <= 0 or h <= 0:
            n_invalid += 1
            continue
        conf = float(p[6]) if len(p) > 6 and p[6] != "" else 1.0
        if len(p) > 7 and p[7] != "":
            classes[int(float(p[7]))] += 1
        if len(p) > 8 and p[8] != "":
            with contextlib.suppress(ValueError):
                vis.append(float(p[8]))
        n_rows += 1
        box = np.array([x, y, x + w, y + h])
        if drop_ignore and conf == 0:
            n_ignore += 1
            ignore[frame].append((tid, box, 0.0))
            continue
        consider[frame].append((tid, box, 1.0))
        ids.add(tid)
        heights.append(h)
    hs = np.array(heights) if heights else np.zeros(1)
    stats = {
        "rows": n_rows,
        "ignore_rows": n_ignore,
        "invalid_rows": n_invalid,
        "frames": len(consider),
        "frame_range": [min(consider), max(consider)] if consider else None,
        "ids": len(ids),
        "class_histogram": dict(sorted(classes.items())),
        "visibility_mean": round(float(np.mean(vis)), 4) if vis else None,
        "bbox_height_px": {
            "p05": round(float(np.percentile(hs, 5)), 1),
            "p50": round(float(np.percentile(hs, 50)), 1),
            "p95": round(float(np.percentile(hs, 95)), 1),
            "min": round(float(hs.min()), 1),
            "max": round(float(hs.max()), 1),
        },
        "boxes_per_frame": {
            "min": min((len(v) for v in consider.values()), default=0),
            "median": float(np.median([len(v) for v in consider.values()])) if consider else 0,
            "max": max((len(v) for v in consider.values()), default=0),
        },
    }
    return dict(consider), dict(ignore), stats


def restrict_frames(frames: Frames, max_frame: int | None) -> Frames:
    if max_frame is None:
        return frames
    return {f: v for f, v in frames.items() if f <= max_frame}


def suppress_in_ignore(pred: Frames, ignore: Frames, iou_min: float) -> Frames:
    """Remove predicted boxes that overlap an ignore box (IoU >= iou_min)."""
    if not ignore:
        return pred
    out: Frames = {}
    for f, dets in pred.items():
        ig = ignore.get(f)
        if not ig or not dets:
            out[f] = list(dets)
            continue
        pb = np.stack([b for _, b, _ in dets])
        ib = np.stack([b for _, b, _ in ig])
        iou = iou_matrix(pb, ib)
        keep = iou.max(axis=1) < iou_min
        kept = [d for d, k in zip(dets, keep, strict=True) if k]
        if kept:
            out[f] = kept
    return out


# --------------------------------------------------------------------- GSR


def _frame_from_image_id(image_id) -> int | None:
    """MOT 1-based frame from a GSR image_id (int 0-based, or '<prefix><6-digit 1-based>')."""
    if isinstance(image_id, bool):
        return None
    if isinstance(image_id, int):
        return image_id + 1
    s = str(image_id).strip()
    if not s.isdigit():
        return None
    if len(s) > 6:
        return int(s[-6:])
    return int(s) + 1


def load_gsr_records(path: Path | str) -> list[dict]:
    """Tolerant GSR loader: spec (flat array) OR as-shipped SoccerNet-COCO object."""
    data = json.loads(Path(path).read_text())
    raw = data.get("annotations", []) if isinstance(data, dict) else data
    out = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        sc = str(r.get("supercategory", "object")).lower()
        if sc in ("pitch", "camera"):
            continue
        attrs = r.get("attributes") if isinstance(r.get("attributes"), dict) else {}
        role = r.get("role", attrs.get("role"))
        team = r.get("team_side", attrs.get("team", attrs.get("team_side")))
        jersey = r.get("jersey_number", attrs.get("jersey"))
        bb = r.get("bbox_image")
        if isinstance(bb, dict):
            box = [bb.get("x"), bb.get("y"), bb.get("w"), bb.get("h")]
        elif isinstance(bb, list | tuple) and len(bb) >= 4:
            box = list(bb[:4])
        else:
            box = None
        frame = _frame_from_image_id(r.get("image_id"))
        if frame is None or box is None or any(v is None for v in box):
            continue
        out.append({
            "frame": frame,
            "track_id": r.get("track_id"),
            "role": str(role).lower() if role is not None else None,
            "team": str(team).lower() if team is not None else None,
            "jersey": jersey,
            "bbox_xywh": [float(v) for v in box],
        })
    return out


def link_gsr_to_mot(
    gt: Frames, gsr: list[dict], iou_min: float = 0.7, sample_stride: int = 25
) -> dict[int, dict]:
    """Majority-vote (role, team) per MOT id from box overlap with GSR records."""
    by_frame: dict[int, list[dict]] = defaultdict(list)
    for r in gsr:
        by_frame[r["frame"]].append(r)
    votes: dict[int, Counter] = defaultdict(Counter)
    for f in sorted(gt)[::max(1, sample_stride)]:
        recs = by_frame.get(f)
        dets = gt.get(f)
        if not recs or not dets:
            continue
        gb = np.stack([b for _, b, _ in dets])
        rb = np.stack([[r["bbox_xywh"][0], r["bbox_xywh"][1],
                        r["bbox_xywh"][0] + r["bbox_xywh"][2],
                        r["bbox_xywh"][1] + r["bbox_xywh"][3]] for r in recs])
        iou = iou_matrix(gb, rb)
        for gi, (tid, _b, _c) in enumerate(dets):
            j = int(np.argmax(iou[gi]))
            if iou[gi, j] >= iou_min:
                votes[tid][(recs[j]["role"], recs[j]["team"])] += 1
    link = {}
    for tid, c in votes.items():
        (role, team), n = c.most_common(1)[0]
        link[tid] = {"role": role, "team": team, "votes": int(n), "total": int(sum(c.values()))}
    return link


def gt_team_labels(link: dict[int, dict]) -> dict[int, str]:
    """{mot_id: team} for players/goalkeepers with a known side (scoring only)."""
    return {
        tid: v["team"] for tid, v in link.items()
        if v.get("team") in ("left", "right") and v.get("role") in ("player", "goalkeeper", None)
    }
