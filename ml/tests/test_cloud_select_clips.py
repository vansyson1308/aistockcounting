import numpy as np

from ml.gate0a.cloud import select_clips as S

CFG = {"clip_seconds": 2.0, "tune_seconds": 1.0, "candidate_stride_seconds": 1.0,
       "crowd_iou": 0.15, "open_min_population_ratio": 0.9}


def _half(fps=25, seconds=20):
    frames = {}
    n = fps * seconds
    for f in range(1, n + 1):
        t = f / fps
        dets = []
        for i in range(6):
            cx = 300 + 6 * i if 6 <= t < 8 else 100 + 120 * i  # clump vs spread
            h = 40 if not (14 <= t < 16) else 16  # FAR: tiny boxes
            dets.append((i + 1, np.array([cx, 100, cx + 20, 100 + h]), 1.0))
        frames[f] = dets
    return frames


def test_roles_are_correct_disjoint_and_deterministic(tmp_path):
    frames = _half()
    w1 = S.select_windows(frames, 25, CFG)
    w2 = S.select_windows(frames, 25, CFG)
    assert w1 == w2
    assert set(w1) == {"DENSE", "FAR", "OPEN", "TUNE"}
    assert 6 * 25 - 25 <= w1["DENSE"]["start_frame"] <= 8 * 25
    assert 14 * 25 - 25 <= w1["FAR"]["start_frame"] <= 16 * 25
    assert w1["OPEN"]["mean_overlap_pairs"] == 0.0
    ws = list(w1.values())
    for i in range(len(ws)):
        for j in range(i + 1, len(ws)):
            assert ws[i]["end_frame"] < ws[j]["start_frame"] or ws[j]["end_frame"] < ws[i]["start_frame"]
    sha = S.freeze(w1, {"source_half": "test"}, tmp_path / "w.yaml")
    doc, sha2 = S.load_frozen(tmp_path / "w.yaml")
    assert sha == sha2 and doc["windows"]["DENSE"]["role"] == "DENSE"
    assert "NOT OFFICIAL" in doc["banner"]
