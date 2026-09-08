"""Pipeline variants P1-P4 (Real) and O1-O4 (Oracle) from cached artifacts.

Reuses the frozen runner primitives (ml.gate0a.runners.run_oracle:
gt_to_detections / run_online / tracker_to_frames / tracker_to_tracklets /
score) and the offline stack (ml.associate). GT identities are used for
SCORING only; Oracle variants receive GT boxes with identities hidden.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import permutations

import numpy as np

from ml.associate import ReconcileConfig
from ml.associate.reconcile import reconcile_with_stats
from ml.associate.team_cluster import assign_teams
from ml.eval.metrics import _frame_matches
from ml.gate0a.cloud.gt_policy import suppress_in_ignore
from ml.gate0a.runners.run_oracle import (
    gt_to_detections,
    run_online,
    score,
    tracker_to_frames,
    tracker_to_tracklets,
)
from ml.track import Detection, TrackerConfig


@dataclass(frozen=True)
class VariantSpec:
    name: str
    source: str  # "real" (detector boxes) | "oracle" (GT boxes, ids hidden)
    use_emb: bool
    team: str  # "none" | "predicted" | "oracle"
    use_offline: bool
    description: str


VARIANTS: dict[str, VariantSpec] = {
    "P1": VariantSpec("P1", "real", False, "none", False, "real detector + MOT"),
    "P2": VariantSpec("P2", "real", True, "none", False, "P1 + real ReID (online appearance)"),
    "P3": VariantSpec("P3", "real", True, "predicted", False,
                      "P2 + predicted team clustering (evaluated; acts inside offline)"),
    "P4": VariantSpec("P4", "real", True, "predicted", True,
                      "P3 + offline reconciliation (full autonomous stack)"),
    "P4_noteam": VariantSpec("P4_noteam", "real", True, "none", True,
                             "P4 without the team veto (ablation)"),
    "O1": VariantSpec("O1", "oracle", False, "none", False, "GT boxes → online tracker"),
    "O2": VariantSpec("O2", "oracle", True, "none", False, "GT boxes + real crops → embeddings → MOT"),
    "O3": VariantSpec("O3", "oracle", True, "predicted", True,
                      "O2 + predicted team + offline reconciliation"),
    "O4": VariantSpec("O4", "oracle", True, "oracle", True,
                      "O4 — ORACLE TEAM UPPER BOUND (labeled diagnostic; never for maturity)"),
}
REAL = ("P1", "P2", "P3", "P4", "P4_noteam")
ORACLE = ("O1", "O2", "O3", "O4")


def det_rows_to_detections(det_frames: dict, emb: dict | None) -> dict[int, list[Detection]]:
    out = {}
    for f, dets in det_frames.items():
        out[f] = [Detection(frame=f, xyxy=box.copy(), score=float(conf),
                            embedding=None if emb is None else emb.get((f, i)))
                  for i, (_tid, box, conf) in enumerate(dets)]
    return out


def tracker_config(base: dict, margin: float, use_emb: bool) -> TrackerConfig:
    return TrackerConfig(
        high_score=float(base["high_score"]), low_score=float(base["low_score"]),
        iou_gate=float(base["iou_gate"]), n_init=int(base["n_init"]),
        max_age=int(base["max_age"]),
        appearance_weight=float(base["appearance_weight"]) if use_emb else 0.0,
        ambiguity_margin=float(margin), ambiguity_terminate=bool(base.get("ambiguity_terminate", True)),
    )


def _oracle_team_map(gt: dict, tracklets, gt_team: dict[int, str]) -> dict[int, int]:
    """Majority GT team per tracklet (O4 only) → {tracklet_id: 0|1}."""
    pred = {}
    for t in tracklets:
        for f, box, s in zip(t.frames, t.boxes, t.scores, strict=True):
            pred.setdefault(int(f), []).append((t.tracklet_id, box, s))
    votes: dict[int, Counter] = defaultdict(Counter)
    for _f, gid, pid in _frame_matches(gt, pred, 0.5):
        team = gt_team.get(gid)
        if team is not None:
            votes[pid][team] += 1
    sides = sorted({v for v in gt_team.values()})
    code = {s: i for i, s in enumerate(sides[:2])}
    return {pid: code[c.most_common(1)[0][0]] for pid, c in votes.items()
            if c.most_common(1)[0][0] in code}


def team_accuracy(gt: dict, pred_pre_map: dict, team_map: dict[int, int],
                  gt_team: dict[int, str]) -> dict:
    """Best 2-permutation agreement between predicted clusters and GT sides."""
    matches = _frame_matches(gt, pred_pre_map, 0.5)
    pairs = [(gt_team[gid], team_map[pid]) for _f, gid, pid in matches
             if gid in gt_team and pid in team_map]
    if not pairs:
        return {"team_accuracy": None, "n_scored_boxes": 0}
    sides = sorted({g for g, _ in pairs})
    best = 0
    for perm in permutations((0, 1)):
        m = dict(zip(sides[:2], perm, strict=False))
        best = max(best, sum(1 for g, p in pairs if m.get(g) == p))
    return {"team_accuracy": round(best / len(pairs), 4), "n_scored_boxes": len(pairs)}


def run_variant(
    spec: VariantSpec, gt: dict, ignore: dict, det_frames: dict | None,
    det_emb: dict | None, gt_emb: dict | None, tracker_base: dict, margin: float,
    offline_cfg: dict, ignore_iou: float, gt_team: dict[int, str] | None = None,
) -> dict:
    if spec.source == "oracle":
        dets = gt_to_detections(gt, gt_emb if spec.use_emb else None)
    else:
        dets = det_rows_to_detections(det_frames, det_emb if spec.use_emb else None)
    cfg = tracker_config(tracker_base, margin, spec.use_emb)
    tracker, secs = run_online(dets, cfg)
    extra: dict = {
        "variant": spec.name, "source": spec.source, "use_emb": spec.use_emb,
        "team_mode": spec.team, "use_offline": spec.use_offline,
        "n_detections": sum(len(v) for v in dets.values()),
        "n_tracklets": len([t for t in tracker.all_tracks() if t.confirmed]),
        "ambiguity_events": len(tracker.ambiguity_events),
        "online_seconds": round(secs, 2),
    }
    pred_pre = tracker_to_frames(tracker)
    tracklets = tracker_to_tracklets(tracker)
    team_map: dict[int, int] = {}
    if spec.team == "predicted":
        team_map, margin_sep = assign_teams(tracklets)
        extra["team_cluster_margin"] = round(float(margin_sep), 4)
    elif spec.team == "oracle" and gt_team:
        team_map = _oracle_team_map(gt, tracklets, gt_team)
    if team_map and gt_team:
        extra.update(team_accuracy(gt, pred_pre, team_map, gt_team))
    if spec.use_offline:
        for t in tracklets:
            t.team = team_map.get(t.tracklet_id) if spec.team != "none" else None
        rc = ReconcileConfig(**offline_cfg)
        if spec.team == "none":
            rc.require_team_match = False
        mapping, stats = reconcile_with_stats(tracklets, rc)
        pred = tracker_to_frames(tracker, id_map=mapping)
        extra.update({f"offline_{k}": v for k, v in stats.items()})
    else:
        pred = pred_pre
    pred = suppress_in_ignore(pred, ignore, ignore_iou)
    return score(gt, pred, extra)


def sweep_margin(
    gt: dict, ignore: dict, det_frames: dict, det_emb: dict, tracker_base: dict,
    grid: list[float], offline_cfg: dict, ignore_iou: float,
) -> tuple[list[dict], float]:
    """P2 on the TUNE window over the frozen grid; select per contract rule."""
    rows = []
    for m in grid:
        r = run_variant(VARIANTS["P2"], gt, ignore, det_frames, det_emb, None,
                        tracker_base, float(m), offline_cfg, ignore_iou)
        rows.append({"ambiguity_margin": float(m), **r})
    best = sorted(rows, key=lambda r: (-r["assa"], r["id_switches"], r["ambiguity_margin"]))[0]
    return rows, float(best["ambiguity_margin"])


def fragmentation(row: dict) -> float:
    return float(row.get("mean_pred_ids_per_gt_track", float("nan")))


def unit_vec(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 0 else v
