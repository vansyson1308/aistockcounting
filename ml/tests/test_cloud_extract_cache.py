import numpy as np

from ml.gate0a.cloud import cache
from ml.gate0a.cloud.extract_clip import (
    check_alignment,
    ffmpeg_extract_cmd,
    slice_gt,
    slice_keyed,
)


def test_slice_gt_renumbers_and_keyed():
    frames = {f: [(1, np.array([0, 0, 1, 1]), 1.0)] for f in range(1, 11)}
    s = slice_gt(frames, 4, 6)
    assert sorted(s) == [1, 2, 3]
    assert sorted(slice_gt(frames, 4, 6, renumber=False)) == [4, 5, 6]
    emb = {(4, 0): "a", (7, 0): "b"}
    assert slice_keyed(emb, 4, 6) == {(1, 0): "a"}


def test_alignment_notes_and_ffmpeg_cmd(tmp_path):
    r = check_alignment(135000, 67500, 25.0, 25.0)
    assert r["ok"] and "restricted" in r["notes"][0]
    assert not check_alignment(10, 10, 25.0, 29.97)["ok"]
    cmd = ffmpeg_extract_cmd(tmp_path / "v.mp4", 101, 200, tmp_path / "c.mp4")
    assert "between(n,100,199)" in " ".join(cmd) and cmd[0] == "ffmpeg"


def test_cache_valid_invalid_missing(tmp_path):
    spec = {"a": 1, "window": {"start_frame": 1}}
    out = tmp_path / "det.txt"
    assert cache.check(tmp_path, "fp", spec, [out])[0] == cache.RECOMPUTE
    out.write_text("x")
    cache.commit(tmp_path, "fp", spec, [out])
    assert cache.check(tmp_path, "fp", spec, [out])[0] == cache.SKIP
    assert cache.check(tmp_path, "fp", {**spec, "a": 2}, [out])[0] == cache.RECOMPUTE
    out.unlink()
    assert cache.check(tmp_path, "fp", spec, [out])[0] == cache.RECOMPUTE
