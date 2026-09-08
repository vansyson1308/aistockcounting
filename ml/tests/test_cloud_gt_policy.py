import json

import numpy as np

from ml.gate0a.cloud import gt_policy as G


def test_load_gt_ignore_rows_and_stats(tmp_path):
    gt = tmp_path / "gt.txt"
    gt.write_text("\n".join([
        "1,1,10,10,20,40,1,1,1", "1,2,100,10,20,40,1,1,0.5", "1,9,500,500,50,50,0,1,1",
        "2,1,12,10,20,40,1,1,1", "2,2,102,10,20,40,1,1,1", "3,3,0,0,0,10,1,1,1",
    ]))
    consider, ignore, stats = G.load_gt(gt)
    assert stats["rows"] == 5 and stats["ignore_rows"] == 1 and stats["invalid_rows"] == 1
    assert stats["ids"] == 2 and stats["class_histogram"] == {1: 5}
    assert 9 not in {t for v in consider.values() for t, _, _ in v}
    assert 9 in {t for v in ignore.values() for t, _, _ in v}
    assert stats["bbox_height_px"]["p50"] == 40.0


def test_suppress_in_ignore_and_restrict():
    ignore = {1: [(9, np.array([500, 500, 550, 550]), 0.0)]}
    pred = {1: [(1, np.array([505, 505, 550, 550]), 0.9), (2, np.array([0, 0, 10, 10]), 0.9)], 2: [(1, np.array([0, 0, 1, 1]), 0.5)]}
    out = G.suppress_in_ignore(pred, ignore, 0.5)
    assert [t for t, _, _ in out[1]] == [2] and 2 in out
    assert list(G.restrict_frames(pred, 1)) == [1]


def test_seqinfo_parse():
    s = G.parse_seqinfo("[Sequence]\nname=118578\nframeRate=25\nseqLength=67500\nimWidth=4096\nimHeight=1504\n")
    assert s == {"name": "118578", "frameRate": 25.0, "seqLength": 67500, "imWidth": 4096, "imHeight": 1504}


def test_gsr_loader_handles_spec_and_shipped_shapes(tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps([
        {"image_id": 0, "track_id": 7, "role": "player", "team_side": "left",
         "jersey_number": 9, "bbox_image": [10, 10, 20, 40]},
    ]))
    shipped = tmp_path / "shipped.json"
    shipped.write_text(json.dumps({"info": {}, "images": [], "categories": [], "annotations": [
        {"image_id": "3000001", "track_id": 7, "supercategory": "object",
         "attributes": {"role": "goalkeeper", "team": "right", "jersey": "1"},
         "bbox_image": {"x": 10, "y": 10, "w": 20, "h": 40, "x_center": 20, "y_center": 30}},
        {"image_id": "3000001", "supercategory": "pitch"},
    ]}))
    a, b = G.load_gsr_records(spec), G.load_gsr_records(shipped)
    assert a[0]["frame"] == 1 and a[0]["team"] == "left"
    assert len(b) == 1 and b[0]["frame"] == 1 and b[0]["role"] == "goalkeeper" and b[0]["team"] == "right"


def test_link_gsr_to_mot_majority_and_team_labels():
    gt = {f: [(1, np.array([10, 10, 30, 50]), 1.0), (2, np.array([200, 10, 220, 50]), 1.0)] for f in range(1, 51)}
    gsr = []
    for f in range(1, 51):
        gsr.append({"frame": f, "track_id": 77, "role": "player", "team": "left", "bbox_xywh": [10, 10, 20, 40]})
        gsr.append({"frame": f, "track_id": 78, "role": "referee", "team": None, "bbox_xywh": [200, 10, 20, 40]})
    link = G.link_gsr_to_mot(gt, gsr, sample_stride=1)
    assert link[1]["team"] == "left" and link[2]["role"] == "referee"
    assert G.gt_team_labels(link) == {1: "left"}
