from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "VietJewelers AI Stock Counting"
    api_prefix: str = "/api/v1"
    app_env: str = "dev"

    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/stockdb"

    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "tray-images"
    minio_secure: bool = False

    model_path: str = "./models/best.onnx"  # backward compatibility
    model_pt_path: str = "./models/best.pt"
    model_onnx_path: str = "./models/best.onnx"
    mock_mode: bool = True
    confidence_threshold: float = 0.25

    max_image_size_mb: int = 10
    cors_origins: str = "http://localhost:3000"
    rate_limit_per_minute: int = 30

    allowed_mime_types: tuple[str, ...] = ("image/jpeg", "image/png")
    allowed_extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png")

    request_timeout_s: int = Field(default=30, ge=5)

    enable_simple_auth: bool = False
    simple_auth_token: str = ""
    inference_concurrency_limit: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
