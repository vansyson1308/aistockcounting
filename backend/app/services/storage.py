import io
import uuid
from pathlib import Path

import boto3
from PIL import Image

from app.core.config import get_settings


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

    def save_image_and_thumbnail(
        self, image_bytes: bytes, filename: str
    ) -> tuple[str, str | None]:
        self.ensure_bucket()

        ext = Path(filename).suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png"}:
            ext = ".jpg"

        object_key = f"uploads/{uuid.uuid4().hex}{ext}"
        content_type = "image/png" if ext == ".png" else "image/jpeg"
        self.client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=image_bytes,
            ContentType=content_type,
        )

        thumbnail_key: str | None = None
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            image.thumbnail((480, 480))
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=80)
            thumbnail_key = f"thumbnails/{uuid.uuid4().hex}.jpg"
            self.client.put_object(
                Bucket=self.bucket,
                Key=thumbnail_key,
                Body=buf.getvalue(),
                ContentType="image/jpeg",
            )
        except Exception:
            thumbnail_key = None

        return object_key, thumbnail_key
