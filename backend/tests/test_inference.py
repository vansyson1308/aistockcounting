import pytest

pytest.importorskip("PIL")

import asyncio

from app.services.inference import InferenceService


def test_mock_inference_deterministic() -> None:
    service = InferenceService()
    payload = b"same-input"
    a = asyncio.run(service.predict(payload))
    b = asyncio.run(service.predict(payload))
    assert a["detected_count"] == b["detected_count"]
    assert a["boxes"] == b["boxes"]
    assert isinstance(a["processing_time_ms"], int)
