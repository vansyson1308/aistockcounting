import importlib.util
import io

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None
    or importlib.util.find_spec("PIL") is None,
    reason="fastapi or pillow not installed",
)


async def _create_record(
    client, monkeypatch, staff_id="S1", tray_id="T1", ai_correct=True
):
    """Helper to create a count record via the API."""
    from PIL import Image

    from app.services.storage import StorageService

    monkeypatch.setattr(
        StorageService,
        "save_image_and_thumbnail",
        lambda self, payload, name: ("uploads/filter.jpg", "thumbnails/filter.jpg"),
    )

    img = Image.new("RGB", (50, 50), "blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")

    count_res = await client.post(
        "/api/v1/count-items",
        files={"image": ("t.jpg", buf.getvalue(), "image/jpeg")},
    )
    count_data = count_res.json()["data"]

    await client.post(
        "/api/v1/save",
        json={
            "image_path": count_data["image_path"],
            "image_thumbnail": count_data["image_thumbnail"],
            "detected_count": count_data["detected_count"],
            "confidence_avg": count_data["confidence_avg"],
            "boxes_json": count_data["boxes"],
            "staff_id": staff_id,
            "tray_id": tray_id,
            "is_ai_correct": ai_correct,
        },
    )


@pytest.mark.asyncio
async def test_filter_by_staff_id(client, monkeypatch):
    """History filter by staff_id returns only matching records."""
    await _create_record(client, monkeypatch, staff_id="STAFF-A", tray_id="T1")
    await _create_record(client, monkeypatch, staff_id="STAFF-B", tray_id="T2")

    res = await client.get("/api/v1/history", params={"staff_id": "STAFF-A"})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["staff_id"] == "STAFF-A"


@pytest.mark.asyncio
async def test_filter_by_tray_id(client, monkeypatch):
    """History filter by tray_id returns only matching records."""
    await _create_record(client, monkeypatch, staff_id="S1", tray_id="TRAY-X")

    res = await client.get("/api/v1/history", params={"tray_id": "TRAY-X"})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["tray_id"] == "TRAY-X"


@pytest.mark.asyncio
async def test_filter_by_ai_correct(client, monkeypatch):
    """History filter by ai_correct returns only matching records."""
    await _create_record(client, monkeypatch, ai_correct=False)

    res = await client.get("/api/v1/history", params={"ai_correct": False})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["is_ai_correct"] is False


@pytest.mark.asyncio
async def test_pagination(client, monkeypatch):
    """History pagination returns correct page and limit."""
    # Create a few records
    for _ in range(3):
        await _create_record(client, monkeypatch)

    res = await client.get("/api/v1/history", params={"page": 1, "limit": 2})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["page"] == 1
    assert data["limit"] == 2
    assert len(data["items"]) <= 2
