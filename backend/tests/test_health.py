import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None,
    reason="fastapi not installed",
)


@pytest.mark.asyncio
async def test_health_returns_ok(client):
    """GET /health returns 200 with status ok."""
    res = await client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_api_health_degraded_when_services_down(client, monkeypatch):
    """GET /api/health returns degraded when DB or MinIO is unreachable."""
    from app.db import database as db_module
    from app.services.storage import StorageService

    # Mock engine.connect to raise
    class FakeEngine:
        def connect(self):
            raise Exception("DB down")

    monkeypatch.setattr(db_module, "engine", FakeEngine())
    monkeypatch.setattr(
        StorageService,
        "ensure_bucket",
        lambda self: (_ for _ in ()).throw(Exception("MinIO down")),
    )

    res = await client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "degraded"
    assert body["checks"]["db"] is False
    assert body["checks"]["minio"] is False


@pytest.mark.asyncio
async def test_api_health_ok_when_services_up(client, monkeypatch):
    """GET /api/health returns ok when both DB and MinIO are reachable."""
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, MagicMock

    from app import main as main_module
    from app.services.storage import StorageService

    # Mock the engine used directly in api_health endpoint
    mock_conn = AsyncMock()
    mock_conn.exec_driver_sql = AsyncMock()

    @asynccontextmanager
    async def fake_connect():
        yield mock_conn

    mock_engine = MagicMock()
    mock_engine.connect = fake_connect
    monkeypatch.setattr(main_module, "engine", mock_engine)
    monkeypatch.setattr(StorageService, "ensure_bucket", lambda self: None)

    res = await client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["checks"]["db"] is True
    assert body["checks"]["minio"] is True
