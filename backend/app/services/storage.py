import io
import logging
import time
import uuid
from pathlib import Path

import boto3
from PIL import Image

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self) -> None:
        s = get_settings()
        self.bucket = s.minio_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=f"{'https' if s.minio_secure else 'http'}://{s.minio_endpoint}",
            aws_access_key_id=s.minio_access_key,
            aws_secret_access_key=s.minio_secret_key,
        )

    def ensure_bucket(self) -> None:
        buckets = [b["Name"] for b in self.client.list_buckets().get("Buckets", [])]
        if self.bucket not in buckets:
            self.client.create_bucket(Bucket=self.bucket)

    def _put_with_retry(
        self, key: str, body: bytes, content_type: str, retries: int = 3
    ) -> None:
        for attempt in range(retries):
            try:
                self.client.put_object(
                    Bucket=self.bucket, Key=key, Body=body, ContentType=content_type
                )
                return
            except Exception:
                if attempt == retries - 1:
                    raise
                wait = 0.5 * (attempt + 1)
                logger.warning(
                    "put_object failed for %s (attempt %d/%d), retrying in %.1fs",
                    key,
                    attempt + 1,
                    retries,
                    wait,
                )
                time.sleep(wait)

    def save_image_and_thumbnail(
        self, image_bytes: bytes, filename: str
    ) -> tuple[str, str | None]:
        self.ensure_bucket()

        ext = Path(filename).suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png"}:
            ext = ".jpg"

        object_key = f"uploads/{uuid.uuid4().hex}{ext}"
        content_type = "image/png" if ext == ".png" else "image/jpeg"
        self._put_with_retry(object_key, image_bytes, content_type)

        thumbnail_key: str | None = None
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            image.thumbnail((480, 480))
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=80)
            thumbnail_key = f"thumbnails/{uuid.uuid4().hex}.jpg"
            self._put_with_retry(thumbnail_key, buf.getvalue(), "image/jpeg")
        except Exception:
            logger.warning(
                "Thumbnail generation failed for %s", object_key, exc_info=True
            )
            thumbnail_key = None

        return object_key, thumbnail_key
