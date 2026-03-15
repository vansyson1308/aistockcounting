import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None
    or importlib.util.find_spec("PIL") is None,
    reason="fastapi or pillow not installed",
)


@pytest.mark.asyncio
async def test_auth_disabled_allows_request(client, monkeypatch, image_bytes):
    """When enable_simple_auth=False (default), all requests pass through."""
    from app.services.storage import StorageService

    monkeypatch.setattr(
        StorageService,
        "save_image_and_thumbnail",
        lambda self, payload, name: ("uploads/auth.jpg", "thumbnails/auth.jpg"),
    )
    res = await client.post(
        "/api/v1/count-items",
        files={"image": ("t.jpg", image_bytes, "image/jpeg")},
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_auth_enabled_with_valid_staff_id(client, monkeypatch, image_bytes):
    """When auth enabled, X-STAFF-ID header grants access."""
    from app.core.config import Settings, get_settings
    from app.services.storage import StorageService

    original = get_settings()
    monkeypatch.setattr(
        "app.core.auth.get_settings",
        lambda: Settings(
            **{
                **{k: v for k, v in original.model_dump().items()},
                "enable_simple_auth": True,
                "simple_auth_token": "secret123",
            }
        ),
    )
    monkeypatch.setattr(
        StorageService,
        "save_image_and_thumbnail",
        lambda self, payload, name: ("uploads/auth.jpg", "thumbnails/auth.jpg"),
    )
    res = await client.post(
        "/api/v1/count-items",
        files={"image": ("t.jpg", image_bytes, "image/jpeg")},
        headers={"X-STAFF-ID": "EMP-001"},
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_auth_enabled_with_valid_token(client, monkeypatch, image_bytes):
    """When auth enabled, correct X-API-TOKEN grants access."""
    from app.core.config import Settings, get_settings
    from app.services.storage import StorageService

    original = get_settings()
    monkeypatch.setattr(
        "app.core.auth.get_settings",
        lambda: Settings(
            **{
                **{k: v for k, v in original.model_dump().items()},
                "enable_simple_auth": True,
                "simple_auth_token": "secret123",
            }
        ),
    )
    monkeypatch.setattr(
        StorageService,
        "save_image_and_thumbnail",
        lambda self, payload, name: ("uploads/auth.jpg", "thumbnails/auth.jpg"),
    )
    res = await client.post(
        "/api/v1/count-items",
        files={"image": ("t.jpg", image_bytes, "image/jpeg")},
        headers={"X-API-TOKEN": "secret123"},
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_auth_enabled_no_credentials_returns_401(client, monkeypatch):
    """When auth enabled, missing credentials returns 401."""
    from app.core.config import Settings, get_settings

    original = get_settings()
    monkeypatch.setattr(
        "app.core.auth.get_settings",
        lambda: Settings(
            **{
                **{k: v for k, v in original.model_dump().items()},
                "enable_simple_auth": True,
                "simple_auth_token": "secret123",
            }
        ),
    )
    res = await client.get("/api/v1/stats")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_auth_enabled_wrong_token_returns_401(client, monkeypatch):
    """When auth enabled, wrong token returns 401."""
    from app.core.config import Settings, get_settings

    original = get_settings()
    monkeypatch.setattr(
        "app.core.auth.get_settings",
        lambda: Settings(
            **{
                **{k: v for k, v in original.model_dump().items()},
                "enable_simple_auth": True,
                "simple_auth_token": "secret123",
            }
        ),
    )
    res = await client.get(
        "/api/v1/stats",
        headers={"X-API-TOKEN": "wrong-token"},
    )
    assert res.status_code == 401
