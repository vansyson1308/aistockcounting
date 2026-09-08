import pytest

from ml.gate0a.cloud import hf_data as H

TREE = [
    {"path": "README.md", "size": 10},
    {"path": "mot", "type": "directory"},
    {"path": "mot/118578/gt/gt.txt", "size": 5_000_000},
    {"path": "mot/118578/seqinfo.ini", "size": 120},
    {"path": "mot/128057/gt/gt.txt", "size": 4_000_000},
    {"path": "gsr/118578/118578_1st.json", "size": 30_000_000},
    {"path": "gsr/118578/118578_2nd.json", "size": 31_000_000},
    {"path": "videos/118578_1st.mp4", "size": 6_000_000_000, "lfs": {"sha256": "abc"}},
    {"path": "videos/118578_2nd.mp4", "size": 6_100_000_000, "lfs": {"sha256": "def"}},
    {"path": "videos/128057_1st.mp4", "size": 6_200_000_000},
]
CFG = {"half_tokens": ["1st", "first"], "video_exts": [".mp4", ".mkv"]}


def test_entries_and_layout():
    e = H.entries_from_tree(TREE)
    assert all(x.path != "mot" for x in e)  # directory skipped
    inv = H.layout_inventory(e)
    assert inv["by_top_level"]["videos"]["files"] == 3
    assert "118578" in inv["match_ids_seen"] and "128057" in inv["match_ids_seen"]


def test_plan_is_narrow_and_half_specific():
    e = H.entries_from_tree(TREE)
    plan = H.plan_download(e, "118578", CFG)
    assert plan["gt"] == {"path": "mot/118578/gt/gt.txt", "size": 5_000_000, "scope": "per_match"}
    assert plan["video"]["path"] == "videos/118578_1st.mp4" and plan["video"]["scope"] == "per_half"
    assert plan["video"]["lfs_sha256"] == "abc"
    assert plan["gsr"] == "gsr/118578/118578_1st.json"
    assert plan["seqinfo"] == "mot/118578/seqinfo.ini"
    assert plan["total_bytes"] == 5_000_000 + 120 + 30_000_000 + 6_000_000_000
    assert not any("128057" in f for f in plan["files"])


def test_per_half_gt_preferred_when_present():
    tree = [*TREE, {"path": "mot/118578_1st/gt/gt.txt", "size": 1}]
    gt = H.find_gt(H.entries_from_tree(tree), "118578", ["1st"])
    assert gt["scope"] == "per_half" and gt["path"] == "mot/118578_1st/gt/gt.txt"


def test_full_match_video_fallback():
    tree = [{"path": "videos/118578.mp4", "size": 9}]
    v = H.find_video(H.entries_from_tree(tree), "118578", ["1st"], [".mp4"])
    assert v["scope"] == "full_match"


def test_forbidden_test_ids_refused():
    with pytest.raises(PermissionError):
        H.assert_not_forbidden(["videos/128057_1st.mp4"], ["128057", "132831"])
    H.assert_not_forbidden(["videos/118578_1st.mp4"], ["128057", "132831"])
