"""Real-pipeline ablation ladder P0..P4 + detection-stride ablation (§8, §15).

Consumes detector output in the MOT det interchange format
(`frame,-1,x,y,w,h,score`) per sequence, plus the sequence video for real
crops when ReID stages are enabled. Stages:

  P1  detector boxes → purity-first online MOT (no appearance)
  P2  + real ReID embeddings (online appearance fusion)
  P3  + offline global reconciliation (appearance/motion, no team veto)
  P4  + predicted team clustering as a reconciliation constraint (full stack)
  (P0, detector-only quality, is covered by px_height_recall.py and by P1's
   DetA. Team evidence acts inside reconciliation in this architecture, so
   the ladder isolates its contribution as P4 minus P3.)

Stride ablation: keep detections only every Nth frame; the tracker bridges
gaps (its Kalman coasting), measuring the §T.3 cadence question with data.

All stages are production-like: no GT identities, no GT team labels, no
manual repair. GT is read only by the scorer.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ml.associate import ReconcileConfig, reconcile
from ml.associate.team_cluster import assign_teams
from ml.eval.metrics import evaluate_tracking
from ml.eval.mot_io import read_mot
from ml.eval.trackeval_wrapper import hota_from_frames
from ml.gate0a.runners.run_oracle import (
    gt_to_detections,
    long_horizon_stats,
    run_online,
    tracker_to_frames,
    tracker_to_tracklets,
)
from ml.track import TrackerConfig


def load_detections(path: Path, stride: int = 1):
    frames = read_mot(path)
    if stride > 1:
        keep = {f for f in frames if (f - 1) % stride == 0}
        frames = {f: v for f, v in frames.items() if f in keep}
    return gt_to_detections(frames)  # ids in det files are -1 and unused


def score(gt, pred, extra):
    m = evaluate_tracking(gt, pred).as_dict()
    m.update({k: round(v, 4) for k, v in hota_from_frames(gt, pred).items()})
    m.update(long_horizon_stats(gt, pred))
    m.update(extra)
    return m


def run_stage(
    gt,
    detections,
    use_embeddings: bool,
    use_team: bool,
    use_offline: bool,
    tracker_cfg: TrackerConfig,
    video: Path | None,
):
    if use_embeddings:
        if video is None:
            return {"skipped": "requires video for real crops (§9)"}
        from ml.reid.embedder import embed_sequence

        det_frames = {
            f: [(0, d.xyxy, d.score) for d in dets]
            for f, dets in detections.items()
        }
        embs = embed_sequence(video, det_frames)
        for f, dets in detections.items():
            for i, d in enumerate(dets):
                d.embedding = embs.get((f, i))

    t0 = time.perf_counter()
    tracker, online_s = run_online(detections, tracker_cfg)
    extra = {"online_seconds": round(online_s, 2)}
    if not use_offline:
        pred = tracker_to_frames(tracker)
        return score(gt, pred, extra)

    tracklets = tracker_to_tracklets(tracker)
    if use_team:
        team_map, margin = assign_teams(tracklets)
        for t in tracklets:
            t.team = team_map.get(t.tracklet_id)
        extra["team_cluster_margin"] = round(margin, 4)
    mapping = reconcile(tracklets, ReconcileConfig())
    pred = tracker_to_frames(tracker, id_map=mapping)
    extra.update(
        {
            "offline_seconds": round(time.perf_counter() - t0 - online_s, 2),
            "n_tracklets_in": len(tracklets),
            "n_canonical_out": len(set(mapping.values())),
        }
    )
    return score(gt, pred, extra)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gt", type=Path, required=True)
    ap.add_argument("--dets", type=Path, required=True)
    ap.add_argument("--video", type=Path, default=None)
    ap.add_argument("--seq-name", default="sequence")
    ap.add_argument("--stages", nargs="+", default=["p1", "p2", "p3", "p4"],
                    choices=["p1", "p2", "p3", "p4"])
    ap.add_argument("--strides", type=int, nargs="*", default=[1],
                    help="detection strides for the cadence ablation (§15)")
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    gt = read_mot(args.gt)
    cfg = TrackerConfig()
    results: dict = {"sequence": args.seq_name, "gt": str(args.gt),
                     "dets": str(args.dets), "tracker_config": vars(cfg),
                     "stages": {}, "stride_ablation": {}}

    stage_spec = {
        "p1": (False, False, False),
        "p2": (True, False, False),
        "p3": (True, False, True),
        "p4": (True, True, True),
    }
    for s in args.stages:
        emb, team, off = stage_spec[s]
        detections = load_detections(args.dets)
        results["stages"][s.upper()] = run_stage(
            gt, detections, emb, team, off, cfg, args.video
        )

    for stride in args.strides:
        if stride == 1:
            continue
        detections = load_detections(args.dets, stride=stride)
        results["stride_ablation"][f"stride_{stride}"] = run_stage(
            gt, detections, False, False, False, cfg, None
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"pipeline_{args.seq_name}.json"
    out.write_text(json.dumps(results, indent=2) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
