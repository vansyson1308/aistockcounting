import numpy as np

from app.services import privacy
from app.services.privacy import FaceBlurrer, blur_faces, sanitize_upload
from tests.fixtures.synth_tray import make_tray


def test_bundled_yunet_loads() -> None:
    assert privacy.BUNDLED_YUNET.exists()
    assert FaceBlurrer.get() is not None


def test_no_faces_keeps_original_bytes() -> None:
    payload = make_tray().jpeg()
    out, faces = sanitize_upload(payload, enabled=True)
    assert faces == 0
    assert out == payload


def test_disabled_skips_detection() -> None:
    payload = make_tray().jpeg()
    assert sanitize_upload(payload, enabled=False) == (payload, 0)


def test_detected_face_region_is_blurred(monkeypatch) -> None:
    img = make_tray().image
    blurrer = FaceBlurrer.get()
    assert blurrer is not None
    monkeypatch.setattr(
        blurrer, "faces", lambda _img: np.array([[100, 100, 80, 80]], np.float32)
    )
    res = blur_faces(img)
    assert res.faces == 1 and res.available
    region = (slice(100, 180), slice(100, 180))
    assert not np.array_equal(res.image[region], img[region])
    far = (slice(700, 760), slice(1000, 1100))
    assert np.array_equal(res.image[far], img[far])  # outside the face: untouched
    out, faces = sanitize_upload(make_tray().jpeg(), enabled=True)
    assert faces == 1 and out[:3] == b"\xff\xd8\xff"


def test_missing_model_degrades_gracefully(monkeypatch) -> None:
    monkeypatch.setattr(FaceBlurrer, "_instance", None)
    res = blur_faces(make_tray().image, model_path="/nonexistent/yunet.onnx")
    assert res.available is False and res.faces == 0
    monkeypatch.setattr(FaceBlurrer, "_instance", None)
