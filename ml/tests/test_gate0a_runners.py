import json

import numpy as np
import pytest

from ml.associate.team_cluster import assign_teams, two_means
from ml.associate.tracklets import Tracklet
from ml.eval.mot_io import write_mot
from ml.gate0a.runners.px_height_recall import bucket
from ml.gate0a.runners.run_oracle import long_horizon_stats
from ml.gate0a.runners.sanity_checks import drop_boxes, permute_ids
from ml.gate0a.runners.select_dense_windows import frame_crowding, select_windows


def _frames(spec):
    out = {}
    for f, dets in spec.items():
        out[f] = [
            (tid, np.array([cx - 10, cy - 20, cx + 10, cy + 20]), 1.0)
            for tid, cx, cy in dets
        ]
    return out


def test_permute_ids_keeps_boxes_changes_ids():
    gt = _frames({f: [(1, 100, 100), (2, 300, 100)] for f in range(20)})
    p = permute_ids(gt, seed=1)
    assert sorted(p) == sorted(gt)
    changed = 0
    for f in gt:
        boxes_gt = sorted(tuple(b) for _, b, _ in gt[f])
        boxes_p = sorted(tuple(b) for _, b, _ in p[f])
        assert boxes_gt == boxes_p
        if [t for t, _, _ in gt[f]] != [t for t, _, _ in p[f]]:
            changed += 1
    assert changed > 0


def test_drop_boxes_fraction():
    gt = _frames({f: [(i, 100 * i, 100) for i in range(1, 11)] for f in range(50)})
    d = drop_boxes(gt, 0.4, seed=0)
    total = sum(len(v) for v in d.values())
    assert abs(total / 500 - 0.6) < 0.08


def test_frame_crowding_counts_pairs_and_groups():
    tight = [
        (1, np.array([0, 0, 20, 40]), 1.0),
        (2, np.array([5, 0, 25, 40]), 1.0),
        (3, np.array([10, 0, 30, 40]), 1.0),
        (4, np.array([500, 0, 520, 40]), 1.0),
    ]
    pairs, largest = frame_crowding(tight, iou_thresh=0.15)
    assert pairs >= 2
    assert largest == 3


def test_select_windows_prefers_crowded_region(tmp_path):
    rows = []
    for f in range(1, 601):
        if 200 <= f < 300:  # crowded burst
            rows += [(f, 1, 100, 100, 20, 40, 1.0), (f, 2, 105, 100, 20, 40, 1.0),
                     (f, 3, 110, 100, 20, 40, 1.0)]
        else:
            rows += [(f, 1, 100, 100, 20, 40, 1.0), (f, 2, 400, 100, 20, 40, 1.0)]
    gt = tmp_path / "gt.txt"
    write_mot(gt, rows)
    wins = select_windows(gt, fps=25, window_s=2.0, top_k=1,
                          min_separation_s=1.0)
    assert len(wins) == 1
    assert 150 <= wins[0]["start_frame"] <= 300


def test_px_height_bucket_recall():
    gt = _frames({1: [(1, 100, 100)]})  # height 40 px
    hit = _frames({1: [(9, 100, 100)]})
    miss = _frames({1: [(9, 900, 900)]})
    rows_hit = bucket(gt, hit, bins=[0, 50, 10_000])
    rows_miss = bucket(gt, miss, bins=[0, 50, 10_000])
    assert rows_hit[0]["n_gt"] == 1 and rows_hit[0]["recall"] == 1.0
    assert rows_miss[0]["recall"] == 0.0


def test_two_means_separates_kits():
    a = np.array([1.0, 0.0, 0.0])
    b = np.array([0.0, 1.0, 0.0])
    embs = np.stack([a, a, a, b, b, b]) + 0.01
    embs /= np.linalg.norm(embs, axis=1, keepdims=True)
    labels, margin = two_means(embs)
    assert len(set(labels[:3])) == 1 and len(set(labels[3:])) == 1
    assert labels[0] != labels[3]
    assert margin > 0.1


def test_assign_teams_maps_tracklets():
    def tr(tid, vec):
        e = np.array(vec) / np.linalg.norm(vec)
        return Tracklet(tid, np.arange(5), np.zeros((5, 4)), np.ones(5),
                        np.stack([e] * 5))

    mapping, _margin = assign_teams(
        [tr(1, [1, 0.05, 0]), tr(2, [1, 0, 0.05]), tr(3, [0, 1, 0.05]),
         tr(4, [0.05, 1, 0])]
    )
    assert mapping[1] == mapping[2]
    assert mapping[3] == mapping[4]
    assert mapping[1] != mapping[3]


def test_long_horizon_stats_fragmentation():
    gt = _frames({f: [(1, 100 + f, 100)] for f in range(10)})
    pred = _frames({f: [(10 if f < 5 else 20, 100 + f, 100)] for f in range(10)})
    s = long_horizon_stats(gt, pred)
    assert s["gt_tracks"] == 1
    assert s["mean_pred_ids_per_gt_track"] == 2.0
    assert s["gt_tracks_single_pred_id"] == 0


def test_make_verdict_blocked_and_decided(tmp_path, monkeypatch):
    from ml.gate0a.runners import make_verdict

    monkeypatch.chdir(tmp_path)
    (tmp_path / "ml/gate0a").mkdir(parents=True)
    (tmp_path / "ml/gate0a/thresholds.yaml").write_text(
        "gate0a:\n  assa_min: 55.0\n  hota_min: 55.0\n  idf1_min: 65.0\n"
        "  identity_integrity_min: 0.90\n  team_cluster_min: 0.95\n"
        "  soccernet_hota_min: 70.0\n  conditional_margin: 8.0\n"
        "  deta_healthy_min: 60.0\n  assa_fail_below: 50.0\n"
        "  identity_integrity_fail_below: 0.80\n"
    )

    out = tmp_path / "verdict.json"
    # BLOCKED path
    import sys

    argv = sys.argv
    sys.argv = ["make_verdict", "--blocked", "no data", "--out", str(out)]
    try:
        make_verdict.main()
    finally:
        sys.argv = argv
    rec = json.loads(out.read_text())
    assert rec["status"] == "BLOCKED" and rec["verdict"] is None

    # DECIDED path
    metrics = tmp_path / "metrics.json"
    metrics.write_text(json.dumps({
        "final_test": {"hota": 60, "deta": 62, "assa": 58, "idf1": 70},
        "long_horizon": {"identity_integrity": 0.93},
        "team": {"player_minute_accuracy": 0.97},
        "dense_audit": {"systemic_failure": False},
        "ablation": {"offline_delta_hota": 2.0},
    }))
    sys.argv = ["make_verdict", "--metrics", str(metrics), "--out", str(out)]
    try:
        make_verdict.main()
    finally:
        sys.argv = argv
    rec = json.loads(out.read_text())
    assert rec["status"] == "DECIDED" and rec["verdict"] == "PASS"


def test_pipeline_p1_on_synthetic_dets(tmp_path):
    from ml.eval.mot_io import read_mot
    from ml.gate0a.runners.run_pipeline import load_detections, run_stage
    from ml.track import TrackerConfig

    rows_gt, rows_det = [], []
    for f in range(1, 41):
        for tid, cx in ((1, 100 + 2 * f), (2, 400 - 2 * f)):
            rows_gt.append((f, tid, cx - 10, 80, 20, 40, 1.0))
            rows_det.append((f, -1, cx - 10, 80, 20, 40, 0.9))
    gt_p, det_p = tmp_path / "gt.txt", tmp_path / "det.txt"
    write_mot(gt_p, rows_gt)
    write_mot(det_p, rows_det)
    gt = read_mot(gt_p)
    m = run_stage(gt, load_detections(det_p), False, False, False,
                  TrackerConfig(), None)
    assert m["hota"] > 0.95
    m2 = run_stage(gt, load_detections(det_p, stride=2), False, False, False,
                   TrackerConfig(), None)
    assert m2["completeness"] < m["completeness"]


def test_prep_v1_sample_converter(tmp_path):
    from ml.gate0a.runners.prep_v1_sample import convert

    src = tmp_path / "bbdf.csv"
    header = [
        "TeamID,0,0,0,0,0,1,1,1,1,1,3,3,3,3,3",
        "PlayerID,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0",
        "Attributes,bb_left,bb_top,bb_width,bb_height,conf,bb_left,bb_top,"
        "bb_width,bb_height,conf,bb_left,bb_top,bb_width,bb_height,conf",
        "frame,,,,,,,,,,,,,,,",
    ]
    data = [f"{f},10,20,5,10,1,50,60,5,10,1,90,95,2,2,1" for f in range(3)]
    src.write_text("\n".join(header + data) + "\n")
    info = convert(src, tmp_path / "out")
    assert info["n_tracks"] == 2  # ball (team 3) excluded
    assert info["n_boxes"] == 6
    gt = (tmp_path / "out/gt.txt").read_text().splitlines()
    assert gt[0].startswith("1,")


@pytest.mark.parametrize("n", [0, 1])
def test_two_means_degenerate(n):
    labels, _margin = two_means(np.ones((n, 3)))
    assert len(labels) == n
