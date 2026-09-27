import io
import importlib.util
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PIL") is None,
    reason="pillow not installed",
)


def _make_jpeg_bytes() -> bytes:
    from PIL import Image

    img = Image.new("RGB", (100, 100), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_storage_save_image_success():
    """StorageService saves image and thumbnail, returns both paths."""
    mock_client = MagicMock()
    mock_client.list_buckets.return_value = {"Buckets": [{"Name": "tray-images"}]}

    with patch("app.services.storage.boto3.client", return_value=mock_client):
        from app.services.storage import StorageService

        svc = StorageService()
        image_bytes = _make_jpeg_bytes()
        image_path, thumbnail_path = svc.save_image_and_thumbnail(
            image_bytes, "test.jpg"
        )

    assert image_path.startswith("uploads/")
    assert image_path.endswith(".jpg")
    assert thumbnail_path is not None
    assert thumbnail_path.startswith("thumbnails/")
    assert mock_client.put_object.call_count == 2


def test_storage_thumbnail_failure_returns_none():
    """If thumbnail generation fails, image_path still returned, thumbnail is None."""
    mock_client = MagicMock()
    mock_client.list_buckets.return_value = {"Buckets": [{"Name": "tray-images"}]}

    call_count = 0

    def side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        # First call is image upload (succeeds), all subsequent are thumbnail retries (fail)
        if call_count >= 2:
            raise Exception("Thumbnail upload failed")

    mock_client.put_object.side_effect = side_effect

    with patch("app.services.storage.boto3.client", return_value=mock_client):
        from app.services.storage import StorageService

        svc = StorageService()
        image_bytes = _make_jpeg_bytes()
        image_path, thumbnail_path = svc.save_image_and_thumbnail(
            image_bytes, "test.jpg"
        )

    assert image_path.startswith("uploads/")
    assert thumbnail_path is None


def test_storage_unknown_extension_normalized():
    """Unknown extensions are normalized to .jpg."""
    mock_client = MagicMock()
    mock_client.list_buckets.return_value = {"Buckets": [{"Name": "tray-images"}]}

    with patch("app.services.storage.boto3.client", return_value=mock_client):
        from app.services.storage import StorageService

        svc = StorageService()
        image_bytes = _make_jpeg_bytes()
        image_path, _ = svc.save_image_and_thumbnail(image_bytes, "test.bmp")

    assert image_path.endswith(".jpg")


def test_s3_backend_uses_region_and_head_bucket(monkeypatch) -> None:
    from unittest.mock import MagicMock

    from app.core import config
    from app.services import storage as storage_module

    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "trayagent-evidence")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-1")
    config.get_settings.cache_clear()
    calls = {}

    def fake_client(service, **kwargs):
        calls.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(storage_module.boto3, "client", fake_client)
    try:
        svc = storage_module.StorageService()
        assert svc.bucket == "trayagent-evidence"
        assert calls == {"region_name": "ap-southeast-1"}  # no static keys on AWS
        svc.ensure_bucket()
        svc.client.head_bucket.assert_called_once_with(Bucket="trayagent-evidence")
        svc.client.create_bucket.assert_not_called()
        svc.put_bytes("evidence/x.jpg", b"123")
        svc.client.put_object.assert_called_once()
    finally:
        monkeypatch.undo()
        config.get_settings.cache_clear()
