import json

import numpy as np
import pytest

from app.services.detector_cv import (
    ClassicalDetector,
    Det,
    DetectorMeta,
    MockDetector,
    OnnxYoloxDetector,
    build_detector,
    letterbox,
    nms,
    yolox_grid_decode,
)
from tests.fixtures.synth_tray import make_tray
from tests.onnx_helpers import write_constant_model, yolox_constant_output


def test_letterbox_topleft_and_center() -> None:
    img = np.zeros((100, 200, 3), np.uint8)
    out, r, pad = letterbox(img, (64, 64), "topleft", 114)
    assert out.shape == (64, 64, 3)
    assert r == pytest.approx(0.32)
    assert pad == (0, 0)
    assert out[63, 0, 0] == 114  # bottom padded
    out, r, pad = letterbox(img, (64, 64), "center", 114)
    assert pad == (0, 16)


def test_yolox_grid_decode_places_box() -> None:
    raw = yolox_constant_output(hits=[(0, 3, 2, 0.9)])[0]
    dec = yolox_grid_decode(raw, (64, 64), (8, 16, 32))
    idx = int(np.argmax(dec[:, 4]))
    cx, cy, w, h = dec[idx, :4]
    assert (cx, cy) == pytest.approx((28.0, 20.0))
    assert (w, h) == pytest.approx((16.0, 16.0))


def test_yolox_grid_decode_rejects_wrong_anchor_count() -> None:
    with pytest.raises(ValueError):
        yolox_grid_decode(np.zeros((10, 6), np.float32), (64, 64), (8, 16, 32))


def test_nms_suppresses_overlaps() -> None:
    dets = [Det(0, 0, 10, 10, 0.9), Det(1, 1, 10, 10, 0.8), Det(50, 50, 10, 10, 0.7)]
    kept = nms(dets, 0.1, 0.5)
    assert len(kept) == 2
    assert kept[0].conf == 0.9


@pytest.mark.parametrize("engine", ["auto", "new", "classic"])
def test_onnx_detector_end_to_end_with_cv2_dnn(tmp_path, engine) -> None:
    const = yolox_constant_output(hits=[(0, 3, 2, 0.9), (1, 1, 1, 0.1)])
    model = write_constant_model(tmp_path / "m.onnx", const)
    det = OnnxYoloxDetector(
        model, DetectorMeta(input_size=(64, 64)), engine=engine, score_thr=0.25
    )
    img = np.zeros((128, 128, 3), np.uint8)  # letterbox ratio 0.5
    out = det.detect(img)
    assert len(out) == 1  # the obj=0.1 hit is below the threshold
    d = out[0]
    assert (d.x, d.y, d.w, d.h) == pytest.approx((40.0, 24.0, 32.0, 32.0), abs=1e-3)
    assert d.conf == pytest.approx(0.9, abs=1e-4)


def test_onnx_detector_decode_in_model(tmp_path) -> None:
    raw = yolox_constant_output(hits=[(0, 3, 2, 0.8)])
    decoded = yolox_grid_decode(raw[0], (64, 64), (8, 16, 32))[None]
    model = write_constant_model(tmp_path / "d.onnx", decoded)
    det = OnnxYoloxDetector(
        model, DetectorMeta(input_size=(64, 64), decode_in_model=True)
    )
    out = det.detect(np.zeros((64, 64, 3), np.uint8))
    assert len(out) == 1
    assert out[0].x == pytest.approx(20.0, abs=1e-3)


def test_build_detector_reads_sidecar_and_hashes(tmp_path) -> None:
    model = write_constant_model(
        tmp_path / "trayagent_v1.onnx", yolox_constant_output()
    )
    (tmp_path / "trayagent_v1.json").write_text(
        json.dumps({"input_size": [64, 64], "version": "v1-test"})
    )
    det, status = build_detector("onnx", model_path=str(model), engine="new")
    assert status.ready and det is not None
    assert status.version == "v1-test"
    assert status.model_sha256 and len(status.model_sha256) == 64
    assert det.detect(np.zeros((64, 64, 3), np.uint8)) == []


def test_build_detector_missing_or_bad_model(tmp_path) -> None:
    det, status = build_detector("onnx", model_path=str(tmp_path / "none.onnx"))
    assert det is None and not status.ready
    bad = tmp_path / "bad.onnx"
    bad.write_bytes(b"not a model")
    det, status = build_detector("onnx", model_path=str(bad))
    assert det is None and not status.ready
    assert status.reason.startswith("load failed")
    det, status = build_detector("nope", model_path="")
    assert det is None and not status.ready


def test_classical_and_mock_are_labelled() -> None:
    det, status = build_detector("classical", model_path="")
    assert status.as_dict()["is_baseline"] is True
    det, status = build_detector("mock", model_path="")
    assert status.as_dict()["is_mock"] is True
    assert isinstance(det, MockDetector)


@pytest.mark.parametrize("seed", [0, 1])
def test_classical_detector_on_synthetic(seed) -> None:
    tray = make_tray(n_items=15, seed=seed)
    dets = ClassicalDetector().detect(tray.image)
    assert len(dets) == tray.count
    assert all(0 < d.conf <= 1 for d in dets)


def test_classical_detector_resolution_limit_misses_tiny_items() -> None:
    # With a coarse input side the tiny items fall under the area floor. This
    # is the failure tile_detect exists for.
    tray = make_tray(n_items=100, item_radius=(7, 9), seed=2)
    coarse = ClassicalDetector(input_side=480).detect(tray.image)
    assert len(coarse) < tray.count * 0.8
