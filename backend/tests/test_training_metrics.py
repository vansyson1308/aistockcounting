import sys
from pathlib import Path

import cv2
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from training.metrics import (  # noqa: E402
    average_precision,
    count_metrics,
    iou_matrix,
    read_yolo_labels,
)


def test_iou_matrix() -> None:
    m = iou_matrix([(0, 0, 10, 10)], [(0, 0, 10, 10), (5, 0, 10, 10), (20, 20, 5, 5)])
    assert m[0, 0] == pytest.approx(1.0)
    assert m[0, 1] == pytest.approx(50 / 150)
    assert m[0, 2] == 0


def test_ap_perfect_and_partial() -> None:
    gts = [[(0, 0, 10, 10), (20, 20, 10, 10)]]
    assert average_precision(
        [[(0, 0, 10, 10, 0.9), (20, 20, 10, 10, 0.8)]], gts
    ) == pytest.approx(1.0)
    # one TP (high score), one FP (higher score): precision 0.5 at recall 0.5
    ap = average_precision([[(50, 50, 10, 10, 0.95), (0, 0, 10, 10, 0.9)]], gts)
    assert ap == pytest.approx(0.25)
    # duplicates count once
    ap_dup = average_precision(
        [[(0, 0, 10, 10, 0.9), (0, 0, 10, 10, 0.8)]], [[(0, 0, 10, 10)]]
    )
    assert ap_dup == pytest.approx(1.0)


def test_count_metrics() -> None:
    m = count_metrics([10, 12, 7], [10, 11, 9])
    assert m["mae"] == pytest.approx(1.0)
    assert m["exact"] == pytest.approx(1 / 3)
    assert m["within1"] == pytest.approx(2 / 3)
    assert m["mean_signed_error"] == pytest.approx(-1 / 3)


def test_read_yolo_labels(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    p.write_text("0 0.5 0.5 0.2 0.4\nbad line\n")
    assert read_yolo_labels(p, 100, 50) == [(40.0, 15.0, 20.0, 20.0)]
    assert read_yolo_labels(tmp_path / "missing.txt", 1, 1) == []


def test_yolo_to_coco_conversion(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    from training.train_yolox import yolo_split_to_coco

    (tmp_path / "images" / "val").mkdir(parents=True)
    (tmp_path / "labels" / "val").mkdir(parents=True)
    import numpy as np

    cv2.imwrite(
        str(tmp_path / "images" / "val" / "a.jpg"), np.zeros((50, 100, 3), np.uint8)
    )
    (tmp_path / "labels" / "val" / "a.txt").write_text("0 0.5 0.5 0.2 0.4\n")
    coco = yolo_split_to_coco(tmp_path, "val")
    assert coco["images"][0] == {
        "id": 1,
        "file_name": "a.jpg",
        "width": 100,
        "height": 50,
    }
    assert coco["annotations"][0]["bbox"] == [40.0, 15.0, 20.0, 20.0]
    assert coco["categories"][0]["name"] == "item"
