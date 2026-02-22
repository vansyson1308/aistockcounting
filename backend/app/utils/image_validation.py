import io
from pathlib import Path

from fastapi import UploadFile, status
from PIL import Image

from app.core.config import get_settings
from app.core.errors import api_error

JPEG_MAGIC = (b"\xff\xd8\xff",)
PNG_MAGIC = (b"\x89PNG\r\n\x1a\n",)


def _validate_magic_bytes(payload: bytes) -> None:
    sig = payload[:8]
    if not any(sig.startswith(m) for m in JPEG_MAGIC + PNG_MAGIC):
        raise api_error(
            status.HTTP_400_BAD_REQUEST, "INVALID_IMAGE", "Invalid image payload."
        )


def validate_file_type(file: UploadFile) -> None:
    settings = get_settings()
    extension = Path(file.filename or "").suffix.lower()
    if (
        file.content_type not in settings.allowed_mime_types
        or extension not in settings.allowed_extensions
    ):
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_FILE_TYPE",
            "Only JPEG/PNG files are supported.",
        )


def validate_file_size(payload: bytes) -> None:
    max_size = get_settings().max_image_size_mb * 1024 * 1024
    if len(payload) > max_size:
        raise api_error(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "FILE_TOO_LARGE",
            "Image size exceeds 10MB limit.",
        )


def validate_decodable_image(payload: bytes) -> None:
    _validate_magic_bytes(payload)
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.verify()
    except Exception:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_IMAGE",
            "Invalid or corrupted image payload.",
        )
