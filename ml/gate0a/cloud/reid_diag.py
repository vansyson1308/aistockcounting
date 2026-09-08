"""Real ReID quality diagnostics on GT-box crops (§17).

GT identity is used for EVALUATION only. Distances are cosine distances of
unit embeddings. Same-team separation is the number that matters for
football (opposing kits are trivially separable).
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np


def by_frame_id(gt_local: dict, gt_emb: dict[tuple[int, int], np.ndarray]) -> dict[int, dict[int, np.ndarray]]:
    out: dict[int, dict[int, np.ndarray]] = defaultdict(dict)
    for f, dets in gt_local.items():
        for i, (gid, _b, _c) in enumerate(dets):
            v = gt_emb.get((f, i))
            if v is not None:
                out[f][gid] = v
    return out


def _stats(d: list[float]) -> dict:
    if not d:
        return {"n": 0}
    a = np.array(d)
    return {"n": int(a.size), "mean": round(float(a.mean()), 4),
            "p10": round(float(np.percentile(a, 10)), 4),
            "p50": round(float(np.percentile(a, 50)), 4),
            "p90": round(float(np.percentile(a, 90)), 4)}


def diagnostics(gt_local: dict, gt_emb: dict, gt_team: dict[int, str] | None,
                deltas: list[int], max_queries: int = 4000, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    fid = by_frame_id(gt_local, gt_emb)
    frames = sorted(fid)
    same_player: dict[int, list[float]] = {d: [] for d in deltas}
    diff_player: list[float] = []
    same_team_diff: list[float] = []
    cross_team: list[float] = []
    top1: dict[int, list[int]] = {d: [] for d in deltas}
    top1_within: dict[int, list[int]] = {d: [] for d in deltas}

    # Same-frame different-player distances (with team split when known).
    for f in frames[:: max(1, len(frames) // 200)]:
        ids = list(fid[f])
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                d = 1.0 - float(np.dot(fid[f][ids[i]], fid[f][ids[j]]))
                diff_player.append(d)
                if gt_team and ids[i] in gt_team and ids[j] in gt_team:
                    (same_team_diff if gt_team[ids[i]] == gt_team[ids[j]] else cross_team).append(d)

    fset = set(frames)
    for delta in deltas:
        queries = [f for f in frames if f + delta in fset]
        if len(queries) > max_queries:
            queries = list(rng.choice(queries, size=max_queries, replace=False))
        for f in queries:
            gallery = fid[f + delta]
            if not gallery:
                continue
            g_ids = list(gallery)
            g_mat = np.stack([gallery[g] for g in g_ids])
            for gid, q in fid[f].items():
                if gid not in gallery:
                    continue
                sims = g_mat @ q
                same_player[delta].append(1.0 - float(sims[g_ids.index(gid)]))
                top1[delta].append(int(g_ids[int(np.argmax(sims))] == gid))
                if gt_team and gid in gt_team:
                    mask = np.array([gt_team.get(g) == gt_team[gid] for g in g_ids])
                    if mask.sum() >= 2:
                        sims_m = np.where(mask, sims, -np.inf)
                        top1_within[delta].append(int(g_ids[int(np.argmax(sims_m))] == gid))

    def sep(a: list[float], b: list[float]) -> float | None:
        if not a or not b:
            return None
        aa = rng.choice(np.array(a), size=min(len(a), 2000), replace=False)
        bb = rng.choice(np.array(b), size=min(len(b), 2000), replace=False)
        return round(float(np.mean(aa[:, None] < bb[None, :])), 4)

    sp1 = same_player[deltas[0]] if deltas else []
    return {
        "same_player_distance": {f"delta_{d}": _stats(v) for d, v in same_player.items()},
        "different_player_same_frame": _stats(diff_player),
        "same_team_different_player": _stats(same_team_diff),
        "cross_team_different_player": _stats(cross_team),
        "top1_retrieval": {f"delta_{d}": (round(float(np.mean(v)), 4) if v else None)
                           for d, v in top1.items()},
        "within_team_top1_retrieval": {f"delta_{d}": (round(float(np.mean(v)), 4) if v else None)
                                       for d, v in top1_within.items()},
        "separation_same_player_vs_same_team_other": sep(sp1, same_team_diff),
        "separation_same_player_vs_any_other": sep(sp1, diff_player),
        "teams_available": bool(gt_team),
    }
