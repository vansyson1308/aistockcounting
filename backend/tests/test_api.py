import importlib.util
import io

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None
    or importlib.util.find_spec("PIL") is None,
    reason="fastapi or pillow not installed",
)


@pytest.mark.asyncio
async def test_count_items_success(client, monkeypatch, image_bytes):
    from app.services.storage import StorageService

    monkeypatch.setattr(
        StorageService,
        "save_image_and_thumbnail",
        lambda self, payload, name: ("uploads/test.jpg", "thumbnails/test.jpg"),
    )

    files = {"image": ("tray.jpg", image_bytes, "image/jpeg")}
    data = {"tray_id": "T1", "staff_id": "S1"}
    res = await client.post("/api/v1/count-items", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["tray_id"] == "T1"
    assert body["data"]["staff_id"] == "S1"


@pytest.mark.asyncio
async def test_count_items_invalid_type(client):
    files = {"image": ("tray.gif", b"gifdata", "image/gif")}
    res = await client.post("/api/v1/count-items", files=files)
    assert res.status_code == 400
    assert res.json()["success"] is False


@pytest.mark.asyncio
async def test_count_items_invalid_image_content(client):
    files = {"image": ("tray.jpg", b"not-an-image", "image/jpeg")}
    res = await client.post("/api/v1/count-items", files=files)
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_IMAGE"


@pytest.mark.asyncio
async def test_save_history_stats_flow(client, monkeypatch):
    from app.services.storage import StorageService

    monkeypatch.setattr(
        StorageService,
        "save_image_and_thumbnail",
        lambda self, payload, name: ("uploads/flow.jpg", "thumbnails/flow.jpg"),
    )

    from PIL import Image

    image = Image.new("RGB", (50, 50), "white")
    b = io.BytesIO()
    image.save(b, format="PNG")

    count_res = await client.post(
        "/api/v1/count-items",
        files={"image": ("t.png", b.getvalue(), "image/png")},
    )
    count_data = count_res.json()["data"]

    save_payload = {
        "image_path": count_data["image_path"],
        "image_thumbnail": count_data["image_thumbnail"],
        "detected_count": count_data["detected_count"],
        "manual_count": count_data["detected_count"],
        "confidence_avg": count_data["confidence_avg"],
        "boxes_json": count_data["boxes"],
        "staff_id": "S2",
        "tray_id": "TR2",
        "is_ai_correct": True,
        "notes": "ok",
    }
    save_res = await client.post("/api/v1/save", json=save_payload)
    assert save_res.status_code == 200

    history_res = await client.get(
        "/api/v1/history", params={"staff_id": "S2", "tray_id": "TR2"}
    )
    assert history_res.status_code == 200
    assert history_res.json()["data"]["total"] == 1

    stats_res = await client.get("/api/v1/stats")
    assert stats_res.status_code == 200
    assert stats_res.json()["data"]["total_records"] == 1


@pytest.mark.asyncio
async def test_history_detail_by_id(client, monkeypatch):
    from app.services.storage import StorageService

    monkeypatch.setattr(
        StorageService,
        "save_image_and_thumbnail",
        lambda self, payload, name: ("uploads/detail.jpg", "thumbnails/detail.jpg"),
    )

    from PIL import Image

    image = Image.new("RGB", (30, 30), "white")
    b = io.BytesIO()
    image.save(b, format="JPEG")

    count_res = await client.post(
        "/api/v1/count-items", files={"image": ("x.jpg", b.getvalue(), "image/jpeg")}
    )
    count_data = count_res.json()["data"]

    save_res = await client.post(
        "/api/v1/save",
        json={
            "image_path": count_data["image_path"],
            "image_thumbnail": count_data["image_thumbnail"],
            "detected_count": count_data["detected_count"],
            "manual_count": count_data["detected_count"],
            "confidence_avg": count_data["confidence_avg"],
            "boxes_json": count_data["boxes"],
        },
    )
    rid = save_res.json()["data"]["id"]

    detail = await client.get(f"/api/v1/history/{rid}")
    assert detail.status_code == 200
    assert detail.json()["data"]["id"] == rid

    missing = await client.get("/api/v1/history/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404
