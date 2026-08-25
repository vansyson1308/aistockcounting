"""Pre-freeze dense-occlusion challenge windows from GROUND TRUTH ONLY (§4).

Selection uses only GT crowding statistics — never model performance:
per frame, count (a) pairwise GT box overlaps with IoU ≥ iou_thresh and
(b) the size of the largest mutually-crowded group (connected component of
the overlap graph). Aggregate over sliding windows; greedily pick the top-K
windows with a minimum temporal separation.

Run on the frozen TEST matches BEFORE any predictions are evaluated; the
output manifest (ml/gate0a/dense_eval_manifest.yaml) is then frozen and
becomes a permanent regression benchmark.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import yaml

from ml.eval.mot_io import read_mot
from ml.track.tracker import iou_matrix


def frame_crowding(dets, iou_thresh: float) -> tuple[int, int]:
    """(n_overlapping_pairs, largest_crowd_size) for one frame's GT boxes."""
    if len(dets) < 2:
        return 0, len(dets)
    boxes = np.stack([b for _, b, _ in dets])
    iou = iou_matrix(boxes, boxes)
    np.fill_diagonal(iou, 0.0)
    adj = iou >= iou_thresh
    n_pairs = int(np.triu(adj, 1).sum())
    # Largest connected component of the overlap graph.
    n = len(dets)
    seen = np.zeros(n, dtype=bool)
    largest = 1
    for start in range(n):
        if seen[start]:
            continue
        stack, comp = [start], 0
        seen[start] = True
        while stack:
            u = stack.pop()
            comp += 1
            for v in np.flatnonzero(adj[u]):
                if not seen[v]:
                    seen[v] = True
                    stack.append(v)
        largest = max(largest, comp)
    return n_pairs, largest


def select_windows(
    gt_path: Path,
    fps: float,
    window_s: float = 15.0,
    top_k: int = 5,
    min_separation_s: float = 30.0,
    iou_thresh: float = 0.15,
) -> list[dict]:
    frames = read_mot(gt_path)
    frame_ids = sorted(frames)
    pairs = {}
    crowd = {}
    for f in frame_ids:
        p, c = frame_crowding(frames[f], iou_thresh)
        pairs[f], crowd[f] = p, c

    win = max(1, int(window_s * fps))
    sep = int(min_separation_s * fps)
    scores = []
    for start_idx in range(0, len(frame_ids) - win + 1, max(1, win // 3)):
        idxs = frame_ids[start_idx : start_idx + win]
        score = float(np.mean([pairs[f] for f in idxs]))
        peak_crowd = int(max(crowd[f] for f in idxs))
        scores.append((score, peak_crowd, idxs[0], idxs[-1]))
    scores.sort(reverse=True)

    chosen: list[dict] = []
    for score, peak_crowd, f0, f1 in scores:
        if len(chosen) >= top_k:
            break
        if any(abs(f0 - c["start_frame"]) < sep for c in chosen):
            continue
        chosen.append(
            {
                "start_frame": int(f0),
                "end_frame": int(f1),
                "start_s": round(f0 / fps, 2),
                "end_s": round(f1 / fps, 2),
                "mean_overlap_pairs": round(score, 3),
                "peak_crowd_size": peak_crowd,
            }
        )
    return sorted(chosen, key=lambda c: c["start_frame"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--seq",
        nargs="+",
        required=True,
        metavar="NAME=GT_PATH",
        help="sequence name = path to its gt.txt (repeatable)",
    )
    ap.add_argument("--fps", type=float, required=True)
    ap.add_argument("--window-s", type=float, default=15.0)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--min-separation-s", type=float, default=30.0)
    ap.add_argument("--iou-thresh", type=float, default=0.15)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    manifest = {
        "method": "GT-only crowding (mean overlapping pairs per window; "
        "no model outputs consulted)",
        "params": {
            "fps": args.fps,
            "window_s": args.window_s,
            "top_k_per_sequence": args.top_k,
            "min_separation_s": args.min_separation_s,
            "iou_thresh": args.iou_thresh,
        },
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "note": args.note,
        "sequences": {},
    }
    for spec in args.seq:
        name, path = spec.split("=", 1)
        manifest["sequences"][name] = select_windows(
            Path(path),
            fps=args.fps,
            window_s=args.window_s,
            top_k=args.top_k,
            min_separation_s=args.min_separation_s,
            iou_thresh=args.iou_thresh,
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(yaml.safe_dump(manifest, sort_keys=False))
    total = sum(len(v) for v in manifest["sequences"].values())
    print(f"wrote {args.out} with {total} windows across "
          f"{len(manifest['sequences'])} sequence(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
