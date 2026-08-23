import numpy as np

from ml.track import Detection, PurityFirstTracker, TrackerConfig


def _box(cx, cy, w=20.0, h=40.0):
    return np.array([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2])


def _emb(seed_vec):
    v = np.array(seed_vec, dtype=np.float64)
    return v / np.linalg.norm(v)


def test_single_object_keeps_one_id():
    tracker = PurityFirstTracker(TrackerConfig(n_init=3))
    ids_seen = set()
    for frame in range(20):
        out = tracker.step(frame, [Detection(frame, _box(50 + 3 * frame, 100), 0.9)])
        ids_seen.update(tid for tid, _, _ in out)
    assert ids_seen == {1}
    tracks = [t for t in tracker.all_tracks() if t.confirmed]
    assert len(tracks) == 1
    assert len(tracks[0].history) == 20


def test_parallel_objects_two_stable_ids():
    tracker = PurityFirstTracker()
    for frame in range(15):
        dets = [
            Detection(frame, _box(50 + 3 * frame, 100), 0.9),
            Detection(frame, _box(50 + 3 * frame, 300), 0.9),
        ]
        tracker.step(frame, dets)
    confirmed = [t for t in tracker.all_tracks() if t.confirmed]
    assert len(confirmed) == 2
    assert all(len(t.history) == 15 for t in confirmed)
    assert not tracker.ambiguity_events


def test_crossing_identical_objects_fragments_not_swaps():
    """Two identical objects converging: purity-first must terminate on
    ambiguity (fragmentation), never silently gamble on an identity."""
    cfg = TrackerConfig(ambiguity_margin=0.3, n_init=2, appearance_weight=0.0)
    tracker = PurityFirstTracker(cfg)
    for frame in range(30):
        # Converge from y=100 and y=260 toward y=180 by frame ~15, then diverge.
        offset = max(0.0, 80.0 - 6.0 * frame) if frame <= 15 else 6.0 * (frame - 15)
        offset = min(offset, 80.0)
        dets = [
            Detection(frame, _box(200, 180 - offset), 0.9),
            Detection(frame, _box(200, 180 + offset), 0.9),
        ]
        tracker.step(frame, dets)
    assert len(tracker.ambiguity_events) >= 1
    # Fragmentation: more tracklets than physical objects, by design.
    assert len(tracker.all_tracks()) > 2


def test_occlusion_gap_reacquires_same_id():
    cfg = TrackerConfig(n_init=2, max_age=10)
    tracker = PurityFirstTracker(cfg)
    tid_before = tid_after = None
    for frame in range(30):
        if 12 <= frame < 17:  # occluded: no detection
            out = tracker.step(frame, [])
            continue
        out = tracker.step(frame, [Detection(frame, _box(100 + 2 * frame, 200), 0.9)])
        if out:
            if frame < 12:
                tid_before = out[0][0]
            elif frame >= 17 and tid_after is None:
                tid_after = out[0][0]
    assert tid_before is not None and tid_after is not None
    assert tid_before == tid_after


def test_low_confidence_detection_sustains_confirmed_track():
    cfg = TrackerConfig(high_score=0.5, low_score=0.1, n_init=2)
    tracker = PurityFirstTracker(cfg)
    for frame in range(10):
        score = 0.9 if frame < 5 else 0.2  # "motion blur" frames
        tracker.step(frame, [Detection(frame, _box(100 + 2 * frame, 200), score)])
    confirmed = [t for t in tracker.all_tracks() if t.confirmed]
    assert len(confirmed) == 1
    assert len(confirmed[0].history) == 10


def test_appearance_separates_crossing_distinct_objects():
    """With distinct embeddings and appearance in the cost, a clean crossing
    stays two tracks with consistent identities (no termination needed)."""
    cfg = TrackerConfig(
        appearance_weight=0.6, ambiguity_margin=0.05, n_init=2, iou_gate=0.05
    )
    tracker = PurityFirstTracker(cfg)
    ea, eb = _emb([1.0, 0.0, 0.0]), _emb([0.0, 1.0, 0.0])
    for frame in range(21):
        ya = 100.0 + 8.0 * frame  # crosses y of b around frame 10
        yb = 260.0 - 8.0 * frame
        tracker.step(
            frame,
            [
                Detection(frame, _box(200, ya), 0.9, embedding=ea),
                Detection(frame, _box(200, yb), 0.9, embedding=eb),
            ],
        )
    confirmed = [t for t in tracker.all_tracks() if t.confirmed]
    long_tracks = [t for t in confirmed if len(t.history) >= 15]
    assert len(long_tracks) == 2
    # Identity consistency: each long track's final y continues its own motion.
    for t in long_tracks:
        first_y = (t.history[0][1][1] + t.history[0][1][3]) / 2
        last_y = (t.history[-1][1][1] + t.history[-1][1][3]) / 2
        assert (last_y - first_y > 100) or (first_y - last_y > 100)


def test_to_mot_rows_shape():
    tracker = PurityFirstTracker(TrackerConfig(n_init=2))
    for frame in range(5):
        tracker.step(frame, [Detection(frame, _box(100 + frame, 100), 0.9)])
    rows = tracker.to_mot_rows()
    assert len(rows) == 5
    frame, tid, _x, _y, w, h, _conf = rows[0]
    assert (frame, tid) == (0, 1)
    assert w > 0 and h > 0
