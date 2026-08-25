"""Oracle-detection association experiments (Gate 0A instructions §5).

GT bounding boxes are fed as perfect detections with IDENTITIES REMOVED;
the tracking stack must recover identity on its own. Stages:

  O1  GT boxes → purity-first online tracker (motion/IoU only)
  O2  O1 + real appearance embeddings (crops from video → ReID backbone)
  O3  O2 + offline global reconciliation
  O4  diagnostic only: O3 + oracle team labels (never a production-like result)

Each stage reports HOTA/DetA/AssA (TrackEval), IDF1, ID switches,
fragmentation, completeness, identity integrity, plus long-horizon stats
(pred-fragments per GT track). Results land in reports/gate0a/oracle/.

O2/O3 require the sequence's video for real crops; when no video is present
the stage is SKIPPED with an explicit reason (never simulated with random
embeddings — §9).
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from ml.associate import ReconcileConfig, Tracklet, reconcile
from ml.eval.metrics import evaluate_tracking
from ml.eval.mot_io import read_mot
from ml.eval.trackeval_wrapper import hota_from_frames
from ml.track import Detection, PurityFirstTracker, TrackerConfig


def gt_to_detections(frames, embeddings=None):
    """Strip identities: {frame: [Detection]} with conf=1.0."""
    out = {}
    for f, dets in frames.items():
        out[f] = [
            Detection(
                frame=f,
                xyxy=box.copy(),
                score=1.0,
                embedding=None
                if embeddings is None
                else embeddings.get((f, i)),
            )
            for i, (_tid, box, _c) in enumerate(dets)
        ]
    return out


def run_online(detections, cfg: TrackerConfig):
    tracker = PurityFirstTracker(cfg)
    t0 = time.perf_counter()
    for f in sorted(detections):
        tracker.step(f, detections[f])
    elapsed = time.perf_counter() - t0
    return tracker, elapsed


def tracker_to_frames(tracker, id_map=None):
    """Tracker output → {frame: [(tid, xyxy, conf)]} (confirmed tracks)."""
    frames = defaultdict(list)
    for t in tracker.all_tracks():
        if not t.confirmed:
            continue
        tid = id_map.get(t.track_id, t.track_id) if id_map else t.track_id
        for f, xyxy, score in t.history:
            frames[f].append((tid, xyxy, score))
    return dict(frames)


def tracker_to_tracklets(tracker, team_of_track=None):
    tracklets = []
    for t in tracker.all_tracks():
        if not t.confirmed or len(t.history) < 2:
            continue
        frames = np.array([h[0] for h in t.history])
        boxes = np.stack([h[1] for h in t.history])
        scores = np.array([h[2] for h in t.history])
        emb = None
        if t.embedding is not None:
            emb = np.stack([t.embedding] * len(frames))
        tracklets.append(
            Tracklet(
                tracklet_id=t.track_id,
                frames=frames,
                boxes=boxes,
                scores=scores,
                embeddings=emb,
                team=None if team_of_track is None else team_of_track.get(t.track_id),
            )
        )
    return tracklets


def long_horizon_stats(gt, pred_frames):
    """Fragmentation of GT identities across predicted ids (matched frames)."""
    from ml.eval.metrics import _frame_matches

    matches = _frame_matches(gt, pred_frames, iou_thresh=0.5)
    per_gt = defaultdict(list)
    for f, gid, pid in matches:
        per_gt[gid].append((f, pid))
    frags = {g: len({pid for _, pid in seq}) for g, seq in per_gt.items()}
    return {
        "gt_tracks": len(frags),
        "mean_pred_ids_per_gt_track": round(
            float(np.mean(list(frags.values()))) if frags else 0.0, 3
        ),
        "max_pred_ids_per_gt_track": max(frags.values(), default=0),
        "gt_tracks_single_pred_id": sum(1 for v in frags.values() if v == 1),
    }


def score(gt, pred_frames, extra: dict) -> dict:
    m = evaluate_tracking(gt, pred_frames).as_dict()
    m.update({k: round(v, 4) for k, v in hota_from_frames(gt, pred_frames).items()})
    m.update(long_horizon_stats(gt, pred_frames))
    m.update(extra)
    return m


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gt", type=Path, required=True)
    ap.add_argument("--seq-name", default="sequence")
    ap.add_argument("--video", type=Path, default=None,
                    help="source video for real crops (enables O2/O3)")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--stages", nargs="+", default=["o1"],
                    choices=["o1", "o2", "o3", "o4"])
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--ambiguity-margin", type=float, default=None,
                    help="override TrackerConfig.ambiguity_margin")
    ap.add_argument("--no-ambiguity-terminate", action="store_true",
                    help="disable purity-first termination (continuity mode)")
    ap.add_argument("--tag", default="", help="suffix for the output filename")
    args = ap.parse_args()

    gt = read_mot(args.gt)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    results: dict = {
        "sequence": args.seq_name,
        "gt": str(args.gt),
        "n_frames": len(gt),
        "n_gt_boxes": sum(len(v) for v in gt.values()),
        "tracker_config": vars(TrackerConfig()),
        "stages": {},
    }

    # O1 — motion/IoU only.
    if "o1" in args.stages:
        dets = gt_to_detections(gt)
        cfg = TrackerConfig(appearance_weight=0.0)
        if args.ambiguity_margin is not None:
            cfg.ambiguity_margin = args.ambiguity_margin
        if args.no_ambiguity_terminate:
            cfg.ambiguity_terminate = False
        results["tracker_config"] = vars(cfg)
        tracker, elapsed = run_online(dets, cfg)
        pred = tracker_to_frames(tracker)
        results["stages"]["O1_motion_only"] = score(
            gt,
            pred,
            {
                "n_tracklets": len([t for t in tracker.all_tracks() if t.confirmed]),
                "ambiguity_events": len(tracker.ambiguity_events),
                "tracking_seconds": round(elapsed, 2),
                "fps_processed": round(len(gt) / elapsed, 1),
            },
        )

    needs_video = {"o2", "o3", "o4"} & set(args.stages)
    if needs_video and args.video is None:
        for s in sorted(needs_video):
            results["stages"][f"{s.upper()}_skipped"] = {
                "reason": "requires real image crops from the sequence video; "
                "no video available in this environment (never simulated with "
                "synthetic embeddings per instructions section 9)"
            }
    elif needs_video:
        # Real-crop embedding path (video + torch backbone), then O2/O3/O4.
        from ml.reid.embedder import embed_sequence  # lazy: torch/cv2 needed

        embeddings = embed_sequence(args.video, gt)
        dets = gt_to_detections(gt, embeddings)
        cfg = TrackerConfig(appearance_weight=0.25)
        tracker, elapsed = run_online(dets, cfg)
        pred = tracker_to_frames(tracker)
        if "o2" in args.stages:
            results["stages"]["O2_with_reid"] = score(
                gt, pred, {"tracking_seconds": round(elapsed, 2)}
            )
        if "o3" in args.stages or "o4" in args.stages:
            tracklets = tracker_to_tracklets(tracker)
            mapping = reconcile(tracklets, ReconcileConfig())
            pred3 = tracker_to_frames(tracker, id_map=mapping)
            results["stages"]["O3_with_offline"] = score(gt, pred3, {
                "n_canonical": len(set(mapping.values())),
            })

    suffix = f"_{args.tag}" if args.tag else ""
    out = args.out_dir / f"oracle_{args.seq_name}{suffix}.json"
    out.write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps({k: {m: v.get(m) for m in ("hota", "assa", "idf1",
          "id_switches", "mean_pred_ids_per_gt_track")}
          for k, v in results["stages"].items() if "hota" in v}, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
