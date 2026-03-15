import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None,
    reason="fastapi not installed",
)


def _save_payload(**overrides):
    base = {
        "image_path": "uploads/abc123.jpg",
        "detected_count": 5,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_save_rejects_path_traversal(client):
    res = await client.post(
        "/api/v1/save", json=_save_payload(image_path="../../etc/passwd")
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_save_rejects_absolute_path(client):
    res = await client.post(
        "/api/v1/save", json=_save_payload(image_path="/etc/passwd.jpg")
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_save_rejects_wrong_prefix(client):
    res = await client.post(
        "/api/v1/save", json=_save_payload(image_path="other/test.jpg")
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_save_accepts_valid_path(client):
    res = await client.post(
        "/api/v1/save", json=_save_payload(image_path="uploads/abc123.jpg")
    )
    assert res.status_code == 200
