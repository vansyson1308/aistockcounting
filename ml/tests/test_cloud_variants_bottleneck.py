import numpy as np

from ml.associate import ReconcileConfig, Tracklet
from ml.associate.reconcile import audit_pairs, reconcile_with_stats
from ml.gate0a.cloud import bottleneck as B
from ml.gate0a.cloud import variants as V
from ml.gate0a.cloud.contract import load_contract

TB = {"high_score": 0.5, "low_score": 0.1, "iou_gate": 0.2, "n_init": 3, "max_age": 30,
      "appearance_weight": 0.25, "ambiguity_terminate": True}
OFF = {"split_eps": 0.35, "merge_max_cost": 0.35, "max_gap_frames": 250, "max_speed_px": 12.0,
       "reach_slack_px": 60.0, "require_team_match": True}


def _tr(tid, f0, f1, cx, vec, team=None):
    n = f1 - f0 + 1
    e = np.array(vec, dtype=float)
    e /= np.linalg.norm(e)
    return Tracklet(tid, np.arange(f0, f1 + 1), np.tile([cx, 0, cx + 10, 20], (n, 1)).astype(float),
                    np.ones(n), np.tile(e, (n, 1)), team=team)


def test_reconcile_with_stats_counts():
    a, b = _tr(1, 1, 20, 100, [1, 0, 0]), _tr(2, 30, 50, 105, [1, 0.05, 0])
    c = _tr(3, 10, 40, 400, [0, 1, 0])  # overlaps both → conflicts
    d = _tr(4, 60, 80, 900, [1, 0, 0])  # far away → gate rejected
    parts = [a, b, c, d]
    audit = audit_pairs(parts, ReconcileConfig(**OFF))
    assert audit["pairs"] == 6 and audit["conflicts"] == 2
    mapping, stats = reconcile_with_stats(parts, ReconcileConfig(**OFF))
    assert mapping[1] == mapping[2] and mapping[3] != mapping[1]
    assert stats["merges_accepted"] == 1 and stats["n_canonical_out"] == 3
    assert stats["merges_rejected"] == stats["gate_rejected"] + stats["cost_rejected"]


def _scene(n_frames=40):
    gt, det, det_emb, gt_emb = {}, {}, {}, {}
    colors = {1: [1, 0, 0], 2: [0, 1, 0]}
    for f in range(1, n_frames + 1):
        gt[f], det[f] = [], []
        for i, tid in enumerate((1, 2)):
            cx = 50 + 3 * f if tid == 1 else 400 - 3 * f
            box = np.array([cx, 80, cx + 20, 120], dtype=float)
            gt[f].append((tid, box, 1.0))
            det[f].append((-1, box + 1.0, 0.9))
            e = np.array(colors[tid], dtype=float)
            det_emb[(f, i)] = e
            gt_emb[(f, i)] = e
    return gt, det, det_emb, gt_emb


def test_variants_run_and_sweep_selects_by_rule():
    gt, det, det_emb, gt_emb = _scene()
    team = {1: "left", 2: "right"}
    for name in ("P1", "P2", "P3", "P4", "P4_noteam"):
        m = V.run_variant(V.VARIANTS[name], gt, {}, det, det_emb, None, TB, 0.05, OFF, 0.5, gt_team=team)
        assert m["hota"] > 0.85 and m["variant"] == name  # n_init delay costs ~2 frames
    m3 = V.run_variant(V.VARIANTS["P3"], gt, {}, det, det_emb, None, TB, 0.05, OFF, 0.5, gt_team=team)
    assert m3["team_accuracy"] == 1.0
    o = V.run_variant(V.VARIANTS["O4"], gt, {}, None, None, gt_emb, TB, 0.05, OFF, 0.5, gt_team=team)
    assert o["hota"] > 0.95 and o["offline_n_tracklets_in"] >= 2
    rows, sel = V.sweep_margin(gt, {}, det, det_emb, TB, [0.0, 0.05, 0.15], OFF, 0.5)
    assert len(rows) == 3 and sel in (0.0, 0.05, 0.15)
    best = max(r["assa"] for r in rows)
    chosen = next(r for r in rows if r["ambiguity_margin"] == sel)
    assert all(r["assa"] <= best for r in rows) and chosen["assa"] == best


def _m(hota, deta, assa, integ=0.9, team_acc=None):
    d = {"hota": hota, "deta": deta, "assa": assa, "identity_integrity": integ}
    if team_acc is not None:
        d["team_accuracy"] = team_acc
    return d


def test_bottleneck_patterns():
    rules = load_contract()["bottleneck_rules"]
    det = {"O1": _m(0.7, 1, 0.6), "O2": _m(0.75, 1, 0.68), "O3": _m(0.8, 1, 0.75),
           "P4": _m(0.4, 0.35, 0.5), "P4_noteam": _m(0.4, 0.35, 0.5), "P3": _m(0.4, 0.35, 0.4, team_acc=0.99)}
    r = B.classify_clip(det, 0.6, {"within_team_top1_retrieval": {"delta_25": 0.9}}, rules, 0.45, 0.85)
    assert r["label"] == "DETECTION-LIMITED"
    reid = {"O1": _m(0.7, 1, 0.6), "O2": _m(0.7, 1, 0.6), "O3": _m(0.7, 1, 0.6, 0.85),
            "P4": _m(0.6, 0.8, 0.55), "P3": _m(0.6, 0.8, 0.5, team_acc=0.99)}
    r = B.classify_clip(reid, 0.95, {"within_team_top1_retrieval": {"delta_25": 0.3}}, rules, 0.45, 0.85)
    assert r["label"] == "REID-LIMITED"
    assoc = {"O1": _m(0.5, 1, 0.3), "O2": _m(0.5, 1, 0.35), "O3": _m(0.55, 1, 0.4, 0.7),
             "P4": _m(0.4, 0.7, 0.3), "P3": _m(0.4, 0.7, 0.3, team_acc=0.99)}
    r = B.classify_clip(assoc, 0.95, {"within_team_top1_retrieval": {"delta_25": 0.9}}, rules, 0.45, 0.85)
    assert r["label"] == "ASSOCIATION-LIMITED"
    healthy = {"O1": _m(0.8, 1, 0.7), "O2": _m(0.85, 1, 0.75), "O3": _m(0.9, 1, 0.8),
               "P4": _m(0.85, 0.9, 0.78), "P3": _m(0.8, 0.9, 0.7, team_acc=0.99)}
    assert B.classify_clip(healthy, 0.95, None, rules, 0.45, 0.85)["label"] == "NONE-DOMINANT"
    agg = B.classify({"OPEN": r, "DENSE": B.classify_clip(det, 0.6, None, rules, 0.45, 0.85)})
    assert agg["dominant"] in ("MIXED", "DETECTION-LIMITED", "ASSOCIATION-LIMITED")
    assert B.classify({})["dominant"] == "UNDETERMINED"
