import cv2


def test_opencv_major_version_is_5() -> None:
    assert cv2.__version__.startswith("5"), cv2.__version__


def test_opencv5_dnn_engine_selector_exists() -> None:
    # The OpenCV 5 DNN engine selector used by services/detector_cv.py
    assert hasattr(cv2.dnn, "ENGINE_AUTO")
    assert hasattr(cv2.dnn, "ENGINE_NEW")
    assert hasattr(cv2.dnn, "ENGINE_CLASSIC")


async def test_health_reports_opencv5(client) -> None:
    res = await client.get("/health")
    body = res.json()
    assert body["opencv"].startswith("5")
    assert body["detector"]["backend"] == "mock"
    assert body["detector"]["is_mock"] is True
