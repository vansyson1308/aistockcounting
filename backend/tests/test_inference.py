import asyncio
import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PIL") is None,
    reason="pillow not installed",
)


def test_mock_inference_deterministic() -> None:
    from app.services.inference import InferenceService

    service = InferenceService()
    payload = b"same-input"
    a = asyncio.run(service.predict(payload))
    b = asyncio.run(service.predict(payload))
    assert a["detected_count"] == b["detected_count"]
    assert a["boxes"] == b["boxes"]
    assert isinstance(a["processing_time_ms"], int)
