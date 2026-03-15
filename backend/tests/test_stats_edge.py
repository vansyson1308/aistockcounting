import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None
    or importlib.util.find_spec("PIL") is None,
    reason="fastapi or pillow not installed",
)


@pytest.mark.asyncio
async def test_stats_with_no_data(client):
    """Stats endpoint with no records returns zeros."""
    res = await client.get("/api/v1/stats")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total_records"] == 0
    assert data["avg_detected_count"] == 0.0
    assert data["avg_manual_count"] == 0.0
    assert data["ai_correct_rate"] == 0.0


@pytest.mark.asyncio
async def test_stats_after_multiple_saves(client, monkeypatch, image_bytes):
    """Stats reflect correct aggregations after multiple saves."""
    from app.services.storage import StorageService

    monkeypatch.setattr(
        StorageService,
        "save_image_and_thumbnail",
        lambda self, payload, name: ("uploads/stats.jpg", "thumbnails/stats.jpg"),
    )

    # Create two records with different counts
    count_res = await client.post(
        "/api/v1/count-items",
        files={"image": ("t.jpg", image_bytes, "image/jpeg")},
    )
    count_data = count_res.json()["data"]

    await client.post(
        "/api/v1/save",
        json={
            "image_path": count_data["image_path"],
            "image_thumbnail": count_data["image_thumbnail"],
            "detected_count": 10,
            "manual_count": 12,
            "confidence_avg": 0.8,
            "boxes_json": count_data["boxes"],
            "is_ai_correct": True,
        },
    )

    await client.post(
        "/api/v1/save",
        json={
            "image_path": count_data["image_path"],
            "image_thumbnail": count_data["image_thumbnail"],
            "detected_count": 20,
            "manual_count": 18,
            "confidence_avg": 0.9,
            "boxes_json": count_data["boxes"],
            "is_ai_correct": False,
        },
    )

    res = await client.get("/api/v1/stats")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total_records"] == 2
    assert data["avg_detected_count"] == 15.0
    assert data["avg_manual_count"] == 15.0
    # One out of two is correct
    assert data["ai_correct_rate"] == 0.5
