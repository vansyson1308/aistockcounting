from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=("settings_",),
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
    model_pt_path: str = "./models/best.pt"  # unused since the OpenCV 5 migration
    model_onnx_path: str = "./models/trayagent_v1.onnx"
    model_meta_path: str = ""  # defaults to <model_onnx_path>.json
    # Detector: onnx (product) | classical (OpenCV baseline) | mock (tests only).
    # Mock is never selected implicitly; MOCK_MODE=true is kept as an alias.
    detector_backend: str = "onnx"
    mock_mode: bool = False
    dnn_engine: str = "auto"  # auto | new | classic (cv2.dnn.ENGINE_*)
    confidence_threshold: float = 0.25
    nms_threshold: float = 0.45

    max_image_size_mb: int = 10
    cors_origins: str = "http://localhost:3000"
    rate_limit_per_minute: int = 30

    allowed_mime_types: tuple[str, ...] = ("image/jpeg", "image/png")
    allowed_extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png")

    request_timeout_s: int = Field(default=30, ge=5)

    enable_simple_auth: bool = False
    simple_auth_token: str = ""
    inference_concurrency_limit: int = 2
    model_version: str = "v0001"

    redis_url: str = "redis://redis:6379/0"
    cache_ttl_seconds: int = 300

    default_tenant_key: str = "default"

    # Storage: "minio" (local, S3 API) or "s3" (AWS, instance role credentials)
    storage_backend: str = "minio"
    s3_bucket: str = ""
    aws_region: str = "ap-southeast-1"

    # Privacy
    face_blur_enabled: bool = True
    face_model_path: str = ""  # empty = bundled YuNet (app/assets)

    # Agent
    agent_enabled: bool = True
    agent_planner: str = "deterministic"  # deterministic | bedrock
    agent_max_steps: int = 5
    agent_time_budget_s: float = 20.0
    bedrock_model_id: str = ""
    bedrock_timeout_s: float = 6.0
    cloudwatch_metrics_enabled: bool = False
    cloudwatch_namespace: str = "TrayAgent"
    kiotviet_client_id: str = ""
    kiotviet_client_secret: str = ""
    kiotviet_retailer: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
