import numpy as np

from ml.gate0a.cloud.detector_adapter import (
    merge_tiles,
    nms_numpy,
    plan_tiles,
    to_mot_det_rows,
)


def test_plan_tiles_covers_frame_with_edge_alignment():
    tiles = plan_tiles(4096, 1504, 896, 128)
    assert all(x1 - x0 == 896 and y1 - y0 == 896 for x0, y0, x1, y1 in tiles)
    assert max(t[2] for t in tiles) == 4096 and max(t[3] for t in tiles) == 1504
    assert min(t[0] for t in tiles) == 0 and len(tiles) == 12
    assert plan_tiles(500, 300, 896, 128) == [(0, 0, 500, 300)]


def test_nms_and_cross_tile_merge():
    boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [50, 50, 60, 60]], dtype=float)
    scores = np.array([0.9, 0.8, 0.7])
    assert list(nms_numpy(boxes, scores, 0.5)) == [0, 2]
    tiles = [(0, 0, 100, 100), (80, 0, 180, 100)]
    per_tile = [(np.array([[85.0, 10.0, 95.0, 30.0]]), np.array([0.6])),
                (np.array([[5.0, 10.0, 15.0, 30.0], [40.0, 40.0, 50.0, 60.0]]), np.array([0.9, 0.5]))]
    b, s = merge_tiles(per_tile, tiles, 0.6)
    assert len(b) == 2 and s[0] == 0.9 and b[0].tolist() == [85.0, 10.0, 95.0, 30.0]
    rows = to_mot_det_rows(3, b, s)
    assert rows[0][:2] == (3, -1) and rows[0][4] == 10.0 and rows[0][5] == 20.0
