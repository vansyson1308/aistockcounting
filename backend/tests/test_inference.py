import asyncio

import pytest

from app.services.detector_cv import DetectorStatus, MockDetector
from app.services.inference import DetectorUnavailable, InferenceService
from tests.fixtures.synth_tray import make_tray


@pytest.fixture(autouse=True)
def _reset_detector():
    InferenceService.reset()
    yield
    InferenceService.reset()


def _settings(monkeypatch, **env):
    from app.core import config

    for k, v in env.items():
        monkeypatch.setenv(k, v)
    config.get_settings.cache_clear()
    return config.get_settings()


def test_mock_inference_deterministic() -> None:
    service = InferenceService()
    payload = make_tray().jpeg()
    a = asyncio.run(service.predict(payload))
    b = asyncio.run(service.predict(payload))
    assert a["detected_count"] == b["detected_count"]
    assert a["boxes"] == b["boxes"]
    assert a["mock_mode"] is True
    assert isinstance(a["processing_time_ms"], int)


def test_missing_model_is_not_ready_and_never_mocks(monkeypatch, tmp_path) -> None:
    _settings(
        monkeypatch,
        DETECTOR_BACKEND="onnx",
        MODEL_ONNX_PATH=str(tmp_path / "missing.onnx"),
    )
    try:
        service = InferenceService()
        status = InferenceService.status()
        assert status["ready"] is False
        assert status["backend"] == "onnx"
        assert status["reason"] == "model file missing"
        with pytest.raises(DetectorUnavailable):
            asyncio.run(service.predict(make_tray().jpeg()))
    finally:
        monkeypatch.undo()
        from app.core import config

        config.get_settings.cache_clear()


def test_mock_mode_alias_is_explicit(monkeypatch) -> None:
    _settings(monkeypatch, DETECTOR_BACKEND="onnx", MOCK_MODE="true")
    try:
        assert InferenceService.status()["backend"] == "mock"
    finally:
        monkeypatch.undo()
        from app.core import config

        config.get_settings.cache_clear()


def test_classical_backend_counts_synthetic_tray(monkeypatch) -> None:
    _settings(monkeypatch, DETECTOR_BACKEND="classical")
    try:
        tray = make_tray(n_items=9, seed=5)
        out = asyncio.run(InferenceService().predict(tray.image))
        assert out["detector_backend"] == "classical"
        assert out["mock_mode"] is False
        assert out["detected_count"] == tray.count
    finally:
        monkeypatch.undo()
        from app.core import config

        config.get_settings.cache_clear()


async def test_count_route_returns_503_when_detector_missing(
    client, monkeypatch
) -> None:
    from app.services.storage import StorageService

    monkeypatch.setattr(
        StorageService,
        "save_image_and_thumbnail",
        lambda self, payload, name: ("uploads/a.jpg", None),
    )
    InferenceService.set_detector(
        None, DetectorStatus("onnx", False, "model file missing")  # type: ignore[arg-type]
    )
    res = await client.post(
        "/api/v1/count-items",
        files={"image": ("t.jpg", make_tray().jpeg(), "image/jpeg")},
    )
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "DETECTOR_UNAVAILABLE"
    health = (await client.get("/health")).json()
    assert health["detector"]["ready"] is False


def test_set_detector_swaps_backend() -> None:
    InferenceService.set_detector(MockDetector(), DetectorStatus("mock", True))
    assert InferenceService.detector().name == "mock"
