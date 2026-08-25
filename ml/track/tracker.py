"""Purity-first online tracker (plan §H).

Clean-room SORT-family tracker written from the published ideas:
two-stage association including low-confidence detections (ByteTrack-style),
optional appearance fusion in the matching cost (BoT-SORT-style), and — the
design choice specific to this product — **ambiguity termination**: when the
best and second-best association candidates are too close to call, the track
is terminated and a fresh one is started instead of gambling. Fragmentation
is repaired offline (ml.associate); a silent identity switch is not.

No camera-motion compensation: cameras are fixed by product design.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

from ml.track.kalman import CenterKalman


@dataclass
class Detection:
    frame: int
    xyxy: np.ndarray  # (4,) float: x1, y1, x2, y2
    score: float
    embedding: np.ndarray | None = None  # L2-normalized appearance vector


@dataclass
class TrackerConfig:
    high_score: float = 0.5
    low_score: float = 0.1
    iou_gate: float = 0.2  # minimum IoU for a feasible match
    n_init: int = 3  # consecutive hits to confirm a track
    max_age: int = 30  # frames a lost track keeps predicting
    appearance_weight: float = 0.25  # cost = (1-w)*(1-IoU) + w*cos_dist
    ambiguity_margin: float = 0.15  # min cost margin best vs runner-up
    ambiguity_terminate: bool = True
    embedding_momentum: float = 0.9  # EMA for track appearance
    size_momentum: float = 0.8  # EMA for box width/height


@dataclass
class AmbiguityEvent:
    frame: int
    track_id: int
    margin: float


@dataclass
class _Track:
    track_id: int
    kalman: CenterKalman
    w: float
    h: float
    last_frame: int
    score: float
    hits: int = 1
    misses: int = 0
    confirmed: bool = False
    embedding: np.ndarray | None = None
    history: list[tuple[int, np.ndarray, float]] = field(default_factory=list)
    end_reason: str = ""

    def predicted_box(self) -> np.ndarray:
        cx, cy = self.kalman.center
        return np.array(
            [cx - self.w / 2, cy - self.h / 2, cx + self.w / 2, cy + self.h / 2]
        )


def iou_matrix(boxes_a: np.ndarray, boxes_b: np.ndarray) -> np.ndarray:
    """Pairwise IoU between (N,4) and (M,4) xyxy boxes."""
    if len(boxes_a) == 0 or len(boxes_b) == 0:
        return np.zeros((len(boxes_a), len(boxes_b)))
    a = boxes_a[:, None, :]
    b = boxes_b[None, :, :]
    x1 = np.maximum(a[..., 0], b[..., 0])
    y1 = np.maximum(a[..., 1], b[..., 1])
    x2 = np.minimum(a[..., 2], b[..., 2])
    y2 = np.minimum(a[..., 3], b[..., 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (a[..., 2] - a[..., 0]) * (a[..., 3] - a[..., 1])
    area_b = (b[..., 2] - b[..., 0]) * (b[..., 3] - b[..., 1])
    union = area_a + area_b - inter
    with np.errstate(divide="ignore", invalid="ignore"):
        iou = np.where(union > 0, inter / union, 0.0)
    return iou


class PurityFirstTracker:
    """Frame-by-frame tracker. Feed detections per frame via `step`.

    Outputs: `step` returns the list of (track_id, xyxy, score) for confirmed
    tracks in that frame. Finished + live tracklets are available from
    `all_tracks()` at the end; ambiguity terminations are logged in
    `ambiguity_events`.
    """

    def __init__(self, config: TrackerConfig | None = None) -> None:
        self.cfg = config or TrackerConfig()
        self._tracks: list[_Track] = []
        self._finished: list[_Track] = []
        self._next_id = 1
        self.ambiguity_events: list[AmbiguityEvent] = []

    # ------------------------------------------------------------------ core

    def step(self, frame: int, detections: list[Detection]) -> list[tuple]:
        for t in self._tracks:
            t.kalman.predict()

        high = [d for d in detections if d.score >= self.cfg.high_score]
        low = [
            d
            for d in detections
            if self.cfg.low_score <= d.score < self.cfg.high_score
        ]

        # Stage 1: all live tracks vs high-confidence detections.
        matches, um_tracks, um_dets, ambiguous = self._associate(
            list(self._tracks), high, use_appearance=True, frame=frame
        )
        for t in ambiguous:
            self._terminate(t, reason="ambiguous")
        for t, di in matches:
            self._update_track(t, high[di], frame)

        # Stage 2: remaining tracks vs low-confidence detections (IoU only).
        m2, um_tracks2, _, ambiguous2 = self._associate(
            um_tracks, low, use_appearance=False, frame=frame
        )
        for t in ambiguous2:
            self._terminate(t, reason="ambiguous")
        for t, di in m2:
            self._update_track(t, low[di], frame)

        # Unmatched tracks age; unmatched high-conf detections spawn tracks.
        for t in um_tracks2:
            t.misses += 1
        for di in um_dets:
            self._spawn(high[di], frame)

        self._reap(frame)

        return [
            (t.track_id, t.history[-1][1], t.history[-1][2])
            for t in self._tracks
            if t.confirmed and t.last_frame == frame
        ]

    # ------------------------------------------------------------- internals

    def _associate(
        self,
        tracks: list[_Track],
        dets: list[Detection],
        use_appearance: bool,
        frame: int,
    ) -> tuple[
        list[tuple[_Track, int]], list[_Track], list[int], list[_Track]
    ]:
        """Pure association: returns (matches, unmatched tracks, unmatched det
        indices, ambiguous tracks). Never mutates tracker state — the caller
        applies updates/terminations, so index/object aliasing cannot skew."""
        if not tracks or not dets:
            return [], list(tracks), list(range(len(dets))), []

        tboxes = np.stack([t.predicted_box() for t in tracks])
        dboxes = np.stack([d.xyxy for d in dets])
        iou = iou_matrix(tboxes, dboxes)
        cost = 1.0 - iou

        w = self.cfg.appearance_weight
        if use_appearance and w > 0:
            app = np.zeros_like(cost)
            has_pair = np.zeros_like(cost, dtype=bool)
            for i, t in enumerate(tracks):
                if t.embedding is None:
                    continue
                for j, d in enumerate(dets):
                    if d.embedding is None:
                        continue
                    app[i, j] = 1.0 - float(np.dot(t.embedding, d.embedding))
                    has_pair[i, j] = True
            cost = np.where(has_pair, (1.0 - w) * cost + w * app, cost)

        feasible = iou >= self.cfg.iou_gate
        BIG = 1e6
        masked = np.where(feasible, cost, BIG)
        rows, cols = linear_sum_assignment(masked)

        matches: list[tuple[_Track, int]] = []
        ambiguous_idx: set[int] = set()
        matched_t: set[int] = set()
        matched_d: set[int] = set()
        for r, c in zip(rows, cols, strict=True):
            if masked[r, c] >= BIG:
                continue
            if self.cfg.ambiguity_terminate and self._is_ambiguous(masked, r, c):
                # The track ends (fragmentation); its detection stays
                # unmatched and spawns a fresh track — offline repair (§I)
                # reconnects with full-match evidence.
                ambiguous_idx.add(r)
                self.ambiguity_events.append(
                    AmbiguityEvent(
                        frame=frame,
                        track_id=tracks[r].track_id,
                        margin=self._margin(masked, r, c),
                    )
                )
                continue
            matches.append((tracks[r], c))
            matched_t.add(r)
            matched_d.add(c)

        um_tracks = [
            tracks[i]
            for i in range(len(tracks))
            if i not in matched_t and i not in ambiguous_idx
        ]
        um_dets = [j for j in range(len(dets)) if j not in matched_d]
        ambiguous = [tracks[i] for i in sorted(ambiguous_idx)]
        return matches, um_tracks, um_dets, ambiguous

    def _margin(self, masked: np.ndarray, r: int, c: int) -> float:
        best = masked[r, c]
        row = np.delete(masked[r, :], c)
        col = np.delete(masked[:, c], r)
        alts = np.concatenate([row, col]) if row.size or col.size else np.array([])
        alts = alts[alts < 1e6]
        if alts.size == 0:
            return float("inf")
        return float(alts.min() - best)

    def _is_ambiguous(self, masked: np.ndarray, r: int, c: int) -> bool:
        return self._margin(masked, r, c) < self.cfg.ambiguity_margin

    def _update_track(self, t: _Track, d: Detection, frame: int) -> None:
        cx = float((d.xyxy[0] + d.xyxy[2]) / 2)
        cy = float((d.xyxy[1] + d.xyxy[3]) / 2)
        t.kalman.update(cx, cy)
        m = self.cfg.size_momentum
        t.w = m * t.w + (1 - m) * float(d.xyxy[2] - d.xyxy[0])
        t.h = m * t.h + (1 - m) * float(d.xyxy[3] - d.xyxy[1])
        t.last_frame = frame
        t.score = d.score
        t.hits += 1
        t.misses = 0
        if not t.confirmed and t.hits >= self.cfg.n_init:
            t.confirmed = True
        if d.embedding is not None:
            if t.embedding is None:
                t.embedding = d.embedding.copy()
            else:
                em = self.cfg.embedding_momentum
                mixed = em * t.embedding + (1 - em) * d.embedding
                norm = np.linalg.norm(mixed)
                if norm > 0:
                    t.embedding = mixed / norm
        t.history.append((frame, d.xyxy.copy(), d.score))

    def _spawn(self, d: Detection, frame: int) -> None:
        cx = float((d.xyxy[0] + d.xyxy[2]) / 2)
        cy = float((d.xyxy[1] + d.xyxy[3]) / 2)
        t = _Track(
            track_id=self._next_id,
            kalman=CenterKalman(cx, cy),
            w=float(d.xyxy[2] - d.xyxy[0]),
            h=float(d.xyxy[3] - d.xyxy[1]),
            last_frame=frame,
            score=d.score,
            embedding=None if d.embedding is None else d.embedding.copy(),
        )
        t.history.append((frame, d.xyxy.copy(), d.score))
        self._next_id += 1
        self._tracks.append(t)

    def _terminate(self, t: _Track, reason: str) -> None:
        t.end_reason = reason
        if t in self._tracks:
            self._tracks.remove(t)
        self._finished.append(t)

    def _reap(self, frame: int) -> None:
        for t in list(self._tracks):
            if t.misses > self.cfg.max_age:
                self._terminate(t, reason="lost")
            elif not t.confirmed and t.misses > 0:
                # A tentative track that misses before confirmation is noise.
                self._terminate(t, reason="tentative-dropped")

    # -------------------------------------------------------------- results

    def all_tracks(self) -> list[_Track]:
        return self._finished + self._tracks

    def to_mot_rows(self, confirmed_only: bool = True) -> list[tuple]:
        """Rows of (frame, track_id, x, y, w, h, score) for eval IO."""
        rows = []
        for t in self.all_tracks():
            if confirmed_only and not t.confirmed:
                continue
            for frame, xyxy, score in t.history:
                rows.append(
                    (
                        frame,
                        t.track_id,
                        float(xyxy[0]),
                        float(xyxy[1]),
                        float(xyxy[2] - xyxy[0]),
                        float(xyxy[3] - xyxy[1]),
                        score,
                    )
                )
        rows.sort(key=lambda r: (r[0], r[1]))
        return rows
