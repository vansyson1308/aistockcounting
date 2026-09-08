import numpy as np

from ml.gate0a.cloud.reid_diag import diagnostics


def test_reid_diagnostics_separates_identities():
    rng = np.random.default_rng(0)
    base = {1: [1, 0, 0, 0], 2: [0, 1, 0, 0], 3: [0, 0, 1, 0], 4: [0, 0, 0, 1]}
    gt, emb = {}, {}
    for f in range(1, 61):
        gt[f] = []
        for i, tid in enumerate(base):
            gt[f].append((tid, np.array([10 * tid, 0, 10 * tid + 5, 10]), 1.0))
            v = np.array(base[tid], dtype=float) + rng.normal(0, 0.05, 4)
            emb[(f, i)] = v / np.linalg.norm(v)
    team = {1: "left", 2: "left", 3: "right", 4: "right"}
    d = diagnostics(gt, emb, team, deltas=[5, 25], max_queries=100)
    assert d["top1_retrieval"]["delta_5"] == 1.0 and d["within_team_top1_retrieval"]["delta_25"] == 1.0
    assert d["separation_same_player_vs_same_team_other"] > 0.99
    assert d["same_player_distance"]["delta_5"]["mean"] < d["different_player_same_frame"]["mean"]
    assert d["teams_available"] is True
