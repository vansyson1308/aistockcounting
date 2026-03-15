import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None,
    reason="fastapi not installed",
)


@pytest.mark.asyncio
async def test_http_exception_returns_structured_error(client):
    """HTTPException (e.g. 404) returns {success: false, error: {code, message}}."""
    res = await client.get("/api/v1/history/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404
    body = res.json()
    assert body["success"] is False
    assert "code" in body["error"]
    assert "message" in body["error"]


@pytest.mark.asyncio
async def test_invalid_uuid_returns_422(client):
    """Invalid UUID path parameter returns 422 validation error."""
    res = await client.get("/api/v1/history/not-a-uuid")
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_invalid_query_params_returns_422(client):
    """Invalid query params (e.g. page=-1) returns 422."""
    res = await client.get("/api/v1/history", params={"page": -1})
    assert res.status_code == 422
