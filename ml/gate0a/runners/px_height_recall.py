"""Player-pixel-height vs detection-recall curve (Gate 0A instructions §7).

Inputs: MOT gt.txt + a detections file in MOT det format
(`frame,-1,x,y,w,h,score,...` — the interchange format every detector
adapter dumps; see ml/gate0a/README.md). Matching: per frame, detections
sorted by score greedily claim the GT box with highest IoU ≥ 0.5.

Outputs per height bin: GT count, recall, matched-detection score stats;
CSV (+ PNG when matplotlib is present). This measured curve replaces the
provisional 20 px detection floor in tools/camsim (instructions §19).
"""

from __future__ import annotations

import argparse
import csv
from itertools import pairwise
from pathlib import Path

import numpy as np

from ml.eval.mot_io import read_mot
from ml.track.tracker import iou_matrix

DEFAULT_BINS = [0, 20, 30, 40, 50, 60, 80, 110, 10_000]


def match_frames(gt, dets, iou_thresh: float = 0.5):
    """Yield (height_px, matched: bool, score_of_match|None) per GT box."""
    for f in sorted(gt):
        g = gt.get(f, [])
        d = sorted(dets.get(f, []), key=lambda t: -t[2])
        if not g:
            continue
        gboxes = np.stack([b for _, b, _ in g])
        taken = np.zeros(len(g), dtype=bool)
        matched = [None] * len(g)
        if d:
            dboxes = np.stack([b for _, b, _ in d])
            iou = iou_matrix(dboxes, gboxes)
            for di in range(len(d)):
                order = np.argsort(-iou[di])
                for gi in order:
                    if iou[di, gi] < iou_thresh:
                        break
                    if not taken[gi]:
                        taken[gi] = True
                        matched[gi] = d[di][2]
                        break
        for gi, (_tid, box, _c) in enumerate(g):
            yield float(box[3] - box[1]), taken[gi], matched[gi]


def bucket(gt, dets, bins=None):
    bins = bins or DEFAULT_BINS
    rows = []
    heights, hits, scores = [], [], []
    for h, m, s in match_frames(gt, dets):
        heights.append(h)
        hits.append(m)
        scores.append(s if s is not None else np.nan)
    heights = np.array(heights)
    hits = np.array(hits)
    scores = np.array(scores, dtype=float)
    for lo, hi in pairwise(bins):
        mask = (heights >= lo) & (heights < hi)
        n = int(mask.sum())
        rec = float(hits[mask].mean()) if n else float("nan")
        sc = scores[mask]
        sc = sc[~np.isnan(sc)]
        rows.append(
            {
                "bin_lo_px": lo,
                "bin_hi_px": hi if hi < 10_000 else "",
                "n_gt": n,
                "recall": round(rec, 4) if n else "",
                "score_mean": round(float(sc.mean()), 4) if len(sc) else "",
                "score_p10": round(float(np.percentile(sc, 10)), 4)
                if len(sc)
                else "",
            }
        )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gt", type=Path, required=True)
    ap.add_argument("--dets", type=Path, required=True)
    ap.add_argument("--detector-name", required=True)
    ap.add_argument("--out-csv", type=Path, required=True)
    ap.add_argument("--bins", type=float, nargs="*", default=None)
    args = ap.parse_args()

    gt = read_mot(args.gt)
    dets = read_mot(args.dets)  # id column ignored (-1 in det files)
    rows = bucket(gt, dets, args.bins)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["detector", *rows[0].keys()])
        w.writeheader()
        for r in rows:
            w.writerow({"detector": args.detector_name, **r})
    for r in rows:
        print(r)
    print(f"wrote {args.out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
