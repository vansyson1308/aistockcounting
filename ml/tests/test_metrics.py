import numpy as np
import pytest

from ml.eval.metrics import evaluate_tracking
from ml.eval.mot_io import read_mot, write_mot


def _frames(spec):
    """spec: {frame: [(id, cx, cy), ...]} → FrameBoxes with 20x40 boxes."""
    out = {}
    for frame, dets in spec.items():
        out[frame] = [
            (tid, np.array([cx - 10, cy - 20, cx + 10, cy + 20]), 1.0)
            for tid, cx, cy in dets
        ]
    return out


def test_perfect_tracking():
    gt = _frames({f: [(1, 100 + f, 100)] for f in range(10)})
    m = evaluate_tracking(gt, gt)
    assert m.idf1 == pytest.approx(1.0)
    assert m.id_switches == 0
    assert m.completeness == pytest.approx(1.0)
    assert m.identity_integrity == pytest.approx(1.0)


def test_single_switch_halves_idf1_and_integrity():
    gt = _frames({f: [(1, 100 + f, 100)] for f in range(10)})
    pred = _frames(
        {f: [(1 if f < 5 else 2, 100 + f, 100)] for f in range(10)}
    )
    m = evaluate_tracking(gt, pred)
    assert m.id_switches == 1
    assert m.idf1 == pytest.approx(0.5)
    assert m.completeness == pytest.approx(1.0)
    assert m.identity_integrity == pytest.approx(0.5)


def test_partial_coverage_keeps_integrity():
    gt = _frames({f: [(1, 100 + f, 100)] for f in range(10)})
    pred = _frames({f: [(7, 100 + f, 100)] for f in range(5)})
    m = evaluate_tracking(gt, pred)
    assert m.completeness == pytest.approx(0.5)
    assert m.identity_integrity == pytest.approx(1.0)  # covered time consistent
    assert m.idf1 == pytest.approx(2 * 5 / (2 * 5 + 0 + 5))


def test_false_positives_penalize_idf1_only():
    gt = _frames({f: [(1, 100 + f, 100)] for f in range(10)})
    pred_spec = {f: [(1, 100 + f, 100)] for f in range(10)}
    for f in range(10):
        pred_spec[f].append((99, 500, 500))  # phantom far away
    pred = _frames(pred_spec)
    m = evaluate_tracking(gt, pred)
    assert m.id_switches == 0
    assert m.completeness == pytest.approx(1.0)
    assert m.identity_integrity == pytest.approx(1.0)
    assert m.idf1 == pytest.approx(2 * 10 / (2 * 10 + 10 + 0))


def test_two_players_swap_counts_switches():
    gt = _frames(
        {f: [(1, 100, 100 + f), (2, 300, 100 + f)] for f in range(10)}
    )
    pred_spec = {}
    for f in range(10):
        a, b = (10, 20) if f < 5 else (20, 10)  # swap halfway
        pred_spec[f] = [(a, 100, 100 + f), (b, 300, 100 + f)]
    pred = _frames(pred_spec)
    m = evaluate_tracking(gt, pred)
    assert m.id_switches == 2
    assert m.identity_integrity == pytest.approx(0.5)


def test_mot_io_roundtrip(tmp_path):
    rows = [
        (1, 1, 10.0, 20.0, 30.0, 40.0, 0.9),
        (1, 2, 50.0, 60.0, 30.0, 40.0, 0.8),
        (2, 1, 12.0, 22.0, 30.0, 40.0, 0.95),
    ]
    path = tmp_path / "pred.txt"
    write_mot(path, rows)
    frames = read_mot(path)
    assert set(frames) == {1, 2}
    assert len(frames[1]) == 2
    tid, xyxy, conf = frames[2][0]
    assert tid == 1
    assert xyxy == pytest.approx([12.0, 22.0, 42.0, 62.0])
    assert conf == pytest.approx(0.95)
