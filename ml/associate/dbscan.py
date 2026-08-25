"""Minimal DBSCAN over a precomputed distance matrix (no sklearn).

O(n^2) — fine for per-tracklet detection counts (hundreds to low thousands).
Labels: cluster ids 0..k-1, or -1 for noise.
"""

from __future__ import annotations

import numpy as np


def dbscan_labels(dist: np.ndarray, eps: float, min_samples: int) -> np.ndarray:
    n = dist.shape[0]
    labels = np.full(n, -2, dtype=int)  # -2 = unvisited, -1 = noise
    neighbors = [np.flatnonzero(dist[i] <= eps) for i in range(n)]
    cluster = -1
    for i in range(n):
        if labels[i] != -2:
            continue
        if len(neighbors[i]) < min_samples:
            labels[i] = -1
            continue
        cluster += 1
        labels[i] = cluster
        seeds = list(neighbors[i])
        k = 0
        while k < len(seeds):
            j = seeds[k]
            k += 1
            if labels[j] == -1:
                labels[j] = cluster
            if labels[j] != -2:
                continue
            labels[j] = cluster
            if len(neighbors[j]) >= min_samples:
                seeds.extend(neighbors[j])
    labels[labels == -2] = -1
    return labels
