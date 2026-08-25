import numpy as np

from ml.associate import ReconcileConfig, Tracklet, reconcile
from ml.associate.reconcile import merge_tracklets, split_tracklet


def _emb(vec):
    v = np.array(vec, dtype=np.float64)
    return v / np.linalg.norm(v)


def _tracklet(tid, start, n, cx, cy, emb, team=None, step=2.0):
    frames = np.arange(start, start + n)
    boxes = np.stack(
        [
            np.array([cx + step * i - 10, cy - 20, cx + step * i + 10, cy + 20])
            for i in range(n)
        ]
    )
    embeddings = np.stack([emb] * n)
    return Tracklet(
        tracklet_id=tid,
        frames=frames,
        boxes=boxes,
        scores=np.full(n, 0.9),
        embeddings=embeddings,
        team=team,
    )


EA = _emb([1.0, 0.05, 0.0])
EB = _emb([0.0, 1.0, 0.05])


def test_split_detects_identity_mixture():
    n = 40
    frames = np.arange(n)
    boxes = np.stack([np.array([100 + i, 100, 120 + i, 140]) for i in range(n)])
    embeddings = np.stack([EA] * 20 + [EB] * 20)
    t = Tracklet(1, frames, boxes, np.full(n, 0.9), embeddings)
    parts, _ = split_tracklet(t, ReconcileConfig(), next_id=2)
    assert len(parts) == 2
    assert parts[0].end < parts[1].start


def test_split_leaves_pure_tracklet_alone():
    t = _tracklet(1, 0, 40, 100, 100, EA)
    parts, _ = split_tracklet(t, ReconcileConfig(), next_id=2)
    assert len(parts) == 1
    assert parts[0].tracklet_id == 1


def test_merge_reconnects_fragmented_track():
    a = _tracklet(1, 0, 30, 100, 100, EA)
    b = _tracklet(2, 40, 30, 100 + 2 * 30 + 10, 100, EA)  # resumes nearby
    c = _tracklet(3, 40, 30, 400, 400, EB)  # different identity
    mapping = reconcile([a, b, c])
    assert mapping[1] == mapping[2]
    assert mapping[3] != mapping[1]


def test_overlapping_tracklets_never_merge():
    a = _tracklet(1, 0, 30, 100, 100, EA)
    b = _tracklet(2, 20, 30, 130, 100, EA)  # same look, but coexists 10 frames
    mapping = reconcile([a, b])
    assert mapping[1] != mapping[2]


def test_reachability_gate_blocks_teleport():
    cfg = ReconcileConfig(max_speed_px=5.0, reach_slack_px=10.0)
    a = _tracklet(1, 0, 20, 100, 100, EA)
    b = _tracklet(2, 25, 20, 5000, 100, EA)  # unreachable in 5 frames
    groups = merge_tracklets([a, b], cfg)
    assert len(groups) == 2


def test_team_veto_blocks_cross_team_merge():
    a = _tracklet(1, 0, 20, 100, 100, EA, team=0)
    b = _tracklet(2, 30, 20, 150, 100, EA, team=1)
    mapping = reconcile([a, b])
    assert mapping[1] != mapping[2]


def test_gap_limit_blocks_stale_merge():
    cfg = ReconcileConfig(max_gap_frames=50)
    a = _tracklet(1, 0, 20, 100, 100, EA)
    b = _tracklet(2, 200, 20, 120, 100, EA)  # gap 180 frames
    groups = merge_tracklets([a, b], cfg)
    assert len(groups) == 2
