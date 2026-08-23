"""Tracklet container for offline reconciliation."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Tracklet:
    tracklet_id: int
    frames: np.ndarray  # (N,) int, strictly increasing
    boxes: np.ndarray  # (N, 4) xyxy
    scores: np.ndarray  # (N,)
    embeddings: np.ndarray | None = None  # (N, D) L2-normalized, or None
    team: int | None = None  # optional team cluster label
    source_ids: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.source_ids:
            self.source_ids = [self.tracklet_id]

    @property
    def start(self) -> int:
        return int(self.frames[0])

    @property
    def end(self) -> int:
        return int(self.frames[-1])

    def mean_embedding(self) -> np.ndarray | None:
        if self.embeddings is None or len(self.embeddings) == 0:
            return None
        m = self.embeddings.mean(axis=0)
        norm = np.linalg.norm(m)
        return m / norm if norm > 0 else m

    def center_at(self, index: int) -> np.ndarray:
        box = self.boxes[index]
        return np.array([(box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0])

    def slice(self, mask: np.ndarray, new_id: int) -> Tracklet:
        return Tracklet(
            tracklet_id=new_id,
            frames=self.frames[mask].copy(),
            boxes=self.boxes[mask].copy(),
            scores=self.scores[mask].copy(),
            embeddings=None if self.embeddings is None else self.embeddings[mask].copy(),
            team=self.team,
            source_ids=list(self.source_ids),
        )


def overlaps(a: Tracklet, b: Tracklet) -> bool:
    """True if the tracklets coexist in any frame (conflict: not same player)."""
    return not (a.end < b.start or b.end < a.start) and bool(
        np.intersect1d(a.frames, b.frames).size
    )
