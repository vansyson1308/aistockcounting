import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None
    or importlib.util.find_spec("PIL") is None,
    reason="fastapi or pillow not installed",
)


@pytest.mark.asyncio
async def test_scan_creates_discrepancy_and_review_resolves(
    client, monkeypatch, image_bytes
):
    from app.services.storage import StorageService

    monkeypatch.setattr(
        StorageService,
        "save_image_and_thumbnail",
        lambda self, payload, name: ("uploads/audit.jpg", "thumbnails/audit.jpg"),
    )

    res = await client.post(
        "/api/v1/scans",
        files={"image": ("tray.jpg", image_bytes, "image/jpeg")},
        data={
            "branch_code": "HN-01",
            "tray_code": "RING-A",
            "staff_id": "EMP-1",
            "expected_count": "99",
            "unit_value": "1000000",
        },
    )

    assert res.status_code == 200
    body = res.json()["data"]
    scan = body["scan"]
    assert scan["branch_code"] == "HN-01"
    assert scan["tray_code"] == "RING-A"
    assert scan["expected_count"] == 99
    assert body["discrepancy"]["status"] == "open"

    review = await client.patch(
        f"/api/v1/scans/{scan['id']}/review",
        json={
            "manual_count": 99,
            "expected_count": 99,
            "unit_value": 1000000,
            "is_ai_correct": False,
            "notes": "Corrected after recount.",
        },
    )
    assert review.status_code == 200
    reviewed = review.json()["data"]
    assert reviewed["scan"]["status"] == "reviewed"
    assert reviewed["scan"]["variance_count"] == 0


@pytest.mark.asyncio
async def test_discrepancy_inbox_and_resolution(client, monkeypatch, image_bytes):
    from app.services.storage import StorageService

    monkeypatch.setattr(
        StorageService,
        "save_image_and_thumbnail",
        lambda self, payload, name: ("uploads/inbox.jpg", "thumbnails/inbox.jpg"),
    )

    scan_res = await client.post(
        "/api/v1/scans",
        files={"image": ("tray.jpg", image_bytes, "image/jpeg")},
        data={"branch_code": "SG-01", "tray_code": "BRACELET-B", "expected_count": "25"},
    )
    discrepancy = scan_res.json()["data"]["discrepancy"]

    inbox = await client.get("/api/v1/discrepancies", params={"branch_code": "SG-01"})
    assert inbox.status_code == 200
    assert inbox.json()["data"]["total"] == 1

    resolved = await client.post(
        f"/api/v1/discrepancies/{discrepancy['id']}/resolve",
        json={
            "status": "resolved",
            "resolution_note": "POS was stale; branch manager confirmed.",
            "resolved_by": "MGR-1",
        },
    )
    assert resolved.status_code == 200
    assert resolved.json()["data"]["status"] == "resolved"


@pytest.mark.asyncio
async def test_kiotviet_snapshot_webhook_idempotency_and_status(client):
    imported = await client.post(
        "/api/v1/integrations/kiotviet/inventory-snapshots",
        json={
            "tenant_key": "default",
            "items": [
                {
                    "branch_code": "HN-01",
                    "tray_code": "RING-A",
                    "sku": "RING-001",
                    "product_name": "Gold ring",
                    "expected_count": 12,
                    "unit_value": 3000000,
                }
            ],
        },
    )
    assert imported.status_code == 200
    assert imported.json()["data"]["imported"] == 1

    payload = {
        "tenant_key": "default",
        "event_key": "kv-evt-1",
        "event_type": "inventory.updated",
        "payload": {"productId": 123},
    }
    first = await client.post("/api/v1/integrations/kiotviet/webhook", json=payload)
    second = await client.post("/api/v1/integrations/kiotviet/webhook", json=payload)
    assert first.json()["data"]["duplicate"] is False
    assert second.json()["data"]["duplicate"] is True

    status = await client.get("/api/v1/integrations/kiotviet/status")
    assert status.status_code == 200
    assert status.json()["data"]["snapshots"] == 1


@pytest.mark.asyncio
async def test_kiotviet_csv_fallback_imports_snapshot(client):
    csv_body = (
        "branch_code,tray_code,sku,product_name,expected_count,unit_value\n"
        "DN-01,NECKLACE-C,SKU-9,Necklace,7,4500000\n"
    )

    imported = await client.post(
        "/api/v1/integrations/kiotviet/csv",
        files={"file": ("stock.csv", csv_body.encode("utf-8"), "text/csv")},
    )

    assert imported.status_code == 200
    assert imported.json()["data"]["imported"] == 1


@pytest.mark.asyncio
async def test_image_object_proxy_validates_path(client, monkeypatch):
    from app.services.storage import StorageService

    monkeypatch.setattr(
        StorageService,
        "get_object_stream",
        lambda self, key: (iter([b"ok"]), "image/jpeg"),
    )

    ok = await client.get("/api/v1/images/object/uploads/proof.jpg")
    assert ok.status_code == 200

    bad = await client.get("/api/v1/images/presigned", params={"path": "uploads/../secret.jpg"})
    assert bad.status_code == 400
