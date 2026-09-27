"""Phase 2 data tooling: ingest, pre-label (CVAT YOLO 1.1), CVAT unpack, split/freeze/verify.

Synthetic trays are used only to exercise the tooling, never as data.
"""

import csv
import json
import sys
import zipfile
from pathlib import Path

import cv2
import pytest

from tests.fixtures.synth_tray import make_tray

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "labeling"))

import cvat_tasks  # noqa: E402
import ingest_raw  # noqa: E402
import prelabel  # noqa: E402
import split_dataset  # noqa: E402


@pytest.fixture
def raw_root(tmp_path: Path) -> Path:
    root = tmp_path / "vj_items"
    for i in range(20):
        sub = "hard" if i % 5 == 0 else ""
        d = root / "raw" / sub
        d.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(
            str(d / f"IMG_{i:03d}.jpg"), make_tray(n_items=6 + i % 4, seed=i).image
        )
    (root / "raw" / "pairs").mkdir()
    cv2.imwrite(str(root / "raw" / "pairs" / "T1_prev.jpg"), make_tray(seed=99).image)
    (root / "raw" / "demo").mkdir()
    cv2.imwrite(str(root / "raw" / "demo" / "A_clean.jpg"), make_tray(seed=98).image)
    return root


def test_ingest_is_content_addressed_and_idempotent(raw_root: Path) -> None:
    s1 = ingest_raw.ingest(raw_root)
    assert s1["pool"] == 20 and s1["hard"] == 4 and s1["pairs"] == 1 and s1["demo"] == 1
    files = sorted((raw_root / "images" / "all").iterdir())
    assert len(files) == 20 and all(len(f.stem) == 12 for f in files)
    s2 = ingest_raw.ingest(raw_root)
    assert s2["pool"] == 20
    assert len(list((raw_root / "images" / "all").iterdir())) == 20
    rows = list(csv.DictReader((raw_root / "manifest.csv").open()))
    assert sum(r["hard"] == "1" for r in rows) == 4
    assert (raw_root / "images" / "demo" / "A_clean.jpg").exists()


def test_prelabel_writes_cvat_yolo11_zip(raw_root: Path, tmp_path: Path) -> None:
    ingest_raw.ingest(raw_root)
    out = tmp_path / "pre.zip"
    stats = prelabel.prelabel(
        raw_root / "images" / "all", out, prelabel.ClassicalBackend()
    )
    assert stats["images"] == 20 and stats["boxes"] > 0
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert {"obj.names", "obj.data", "train.txt"} <= set(names)
        txts = [n for n in names if n.startswith("obj_train_data/")]
        assert len(txts) == 20
        line = zf.read(txts[0]).decode().splitlines()[0].split()
        assert line[0] == "0" and all(0 < float(v) < 1 for v in line[1:])


def test_yolo_lines_normalisation() -> None:
    assert prelabel.yolo_lines([(10, 20, 30, 40, 0.9)], 100, 200) == [
        "0 0.250000 0.200000 0.300000 0.200000"
    ]


def _labeled_pool(raw_root: Path, tmp_path: Path) -> int:
    n = ingest_raw.ingest(raw_root)["pool"]
    out = tmp_path / "pre.zip"
    prelabel.prelabel(raw_root / "images" / "all", out, prelabel.ClassicalBackend())
    # stands in for "human-reviewed CVAT export" in this test
    assert cvat_tasks.unpack_export(out, raw_root / "labels" / "all") == n
    return n


def test_split_70_15_15_stratified_and_frozen(raw_root: Path, tmp_path: Path) -> None:
    _labeled_pool(raw_root, tmp_path)
    counts = split_dataset.split(raw_root, 42, (0.7, 0.15, 0.15))
    assert counts == {"train": 14, "val": 3, "test": 3}
    info = json.loads((raw_root / "splits" / "SPLIT_INFO.json").read_text())
    assert all(v >= 0 for v in info["hard_per_split"].values())
    assert info["hard_per_split"]["train"] >= 2
    assert split_dataset.verify(raw_root) == []
    test_before = (raw_root / "splits" / "test.txt").read_text()

    # Same seed, same assignment. Adding new photos never changes the frozen test set.
    cv2.imwrite(str(raw_root / "raw" / "IMG_new.jpg"), make_tray(seed=123).image)
    _labeled_pool(raw_root, tmp_path)
    counts2 = split_dataset.split(raw_root, 7, (0.7, 0.15, 0.15))
    assert counts2["test"] == 3 and sum(counts2.values()) == 21
    assert (raw_root / "splits" / "test.txt").read_text() == test_before
    assert split_dataset.verify(raw_root) == []


def test_verify_detects_tampering(raw_root: Path, tmp_path: Path) -> None:
    _labeled_pool(raw_root, tmp_path)
    split_dataset.split(raw_root, 42, (0.7, 0.15, 0.15))
    label = next((raw_root / "labels" / "test").iterdir())
    label.write_text("0 0.5 0.5 0.1 0.1\n")
    problems = split_dataset.verify(raw_root)
    assert problems and problems[0].startswith("changed:")


def test_split_refuses_unlabeled_images(raw_root: Path) -> None:
    ingest_raw.ingest(raw_root)
    (raw_root / "labels" / "all").mkdir(parents=True)
    with pytest.raises(SystemExit):
        split_dataset.split(raw_root, 42, (0.7, 0.15, 0.15))


def test_assign_is_deterministic() -> None:
    names = [f"{i:03d}.jpg" for i in range(40)]
    a = split_dataset.assign(names, {"000.jpg", "005.jpg"}, (0.7, 0.15, 0.15), 42)
    b = split_dataset.assign(names, {"000.jpg", "005.jpg"}, (0.7, 0.15, 0.15), 42)
    assert a == b
    assert sum(v == "test" for v in a.values()) == 6
