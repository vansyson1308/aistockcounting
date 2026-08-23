"""Predicted team clustering from appearance embeddings (plan section K L2).

Production-like: never consumes ground-truth team labels (GT teams are used
only for SCORING). Simple, deterministic 2-means over per-tracklet mean
embeddings with a farthest-pair initialization; per-tracklet assignment with
a separation-margin diagnostic (a QA signal in the platform).

This is the Gate 0A seed: crop-level color/embedding clustering with role
priors (GK/referee) lands with the full identity phase.
"""

from __future__ import annotations

import numpy as np

from ml.associate.tracklets import Tracklet


def two_means(embs: np.ndarray, iters: int = 50) -> tuple[np.ndarray, float]:
    """Deterministic 2-means on unit vectors → (labels, separation margin)."""
    if len(embs) < 2:
        return np.zeros(len(embs), dtype=int), 0.0
    # Farthest-pair init (deterministic).
    dots = embs @ embs.T
    i, j = np.unravel_index(np.argmin(dots), dots.shape)
    centers = np.stack([embs[i], embs[j]])
    labels = np.zeros(len(embs), dtype=int)
    for _ in range(iters):
        sims = embs @ centers.T
        new_labels = np.argmax(sims, axis=1)
        if np.array_equal(new_labels, labels) and _ > 0:
            break
        labels = new_labels
        for k in (0, 1):
            members = embs[labels == k]
            if len(members):
                c = members.mean(axis=0)
                centers[k] = c / max(np.linalg.norm(c), 1e-9)
    sims = embs @ centers.T
    margin = float(np.mean(np.abs(sims[:, 0] - sims[:, 1])))
    return labels, margin


def assign_teams(tracklets: list[Tracklet]) -> tuple[dict[int, int], float]:
    """Cluster tracklets into two teams. Returns ({tracklet_id: 0|1}, margin).

    Tracklets without embeddings are left unassigned (absent from the map).
    """
    ids, vecs = [], []
    for t in tracklets:
        e = t.mean_embedding()
        if e is not None:
            ids.append(t.tracklet_id)
            vecs.append(e)
    if not ids:
        return {}, 0.0
    labels, margin = two_means(np.stack(vecs))
    return dict(zip(ids, (int(x) for x in labels), strict=True)), margin
