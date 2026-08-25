import numpy as np
import pytest

from ml.eval.trackeval_wrapper import TrackEvalUnavailable, hota_from_frames

trackeval = pytest.importorskip(
    "trackeval",
    reason="official TrackEval not installed (ml/requirements-dev.txt installs it "
    "from GitHub; CI runs this test)",
)


def _frames(spec):
    out = {}
    for frame, dets in spec.items():
        out[frame] = [
            (tid, np.array([cx - 10, cy - 20, cx + 10, cy + 20]), 1.0)
            for tid, cx, cy in dets
        ]
    return out


def test_perfect_tracking_scores_one():
    gt = _frames({f: [(1, 100 + f, 100), (2, 300, 100 + f)] for f in range(10)})
    scores = hota_from_frames(gt, gt)
    assert scores["hota"] == pytest.approx(1.0, abs=1e-6)
    assert scores["deta"] == pytest.approx(1.0, abs=1e-6)
    assert scores["assa"] == pytest.approx(1.0, abs=1e-6)


def test_identity_switch_lowers_assa_not_deta():
    gt = _frames({f: [(1, 100 + f, 100)] for f in range(20)})
    pred = _frames({f: [(1 if f < 10 else 2, 100 + f, 100)] for f in range(20)})
    scores = hota_from_frames(gt, pred)
    assert scores["deta"] == pytest.approx(1.0, abs=1e-6)
    assert scores["assa"] < 0.75


def test_unavailable_error_is_informative():
    assert "TrackEval" in TrackEvalUnavailable().args[0]
