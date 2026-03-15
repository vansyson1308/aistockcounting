from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.count import Box


def _validate_safe_path(v: str, allowed_prefix: str) -> str:
    if ".." in v:
        raise ValueError("Path must not contain '..'")
    if v.startswith("/") or v.startswith("\\"):
        raise ValueError("Path must not be absolute")
    if not v.startswith(allowed_prefix):
        raise ValueError(f"Path must start with '{allowed_prefix}'")
    if not v.lower().endswith((".jpg", ".jpeg", ".png")):
        raise ValueError("Path must end with .jpg, .jpeg, or .png")
    return v


class SaveRequest(BaseModel):
    image_path: str = Field(max_length=500)
    image_thumbnail: str | None = Field(default=None, max_length=500)
    detected_count: int = Field(ge=0)
    manual_count: int | None = Field(default=None, ge=0)
    confidence_avg: float | None = Field(default=None, ge=0, le=1)
    boxes_json: list[Box] = Field(default_factory=list)
    staff_id: str | None = Field(default=None, max_length=50)
    tray_id: str | None = Field(default=None, max_length=50)
    is_ai_correct: bool | None = None
    notes: str | None = Field(default=None, max_length=500)
    model_version: str | None = Field(default=None, max_length=50)
    processing_time_ms: int | None = Field(default=None, ge=0)

    @field_validator("image_path")
    @classmethod
    def validate_image_path(cls, v: str) -> str:
        return _validate_safe_path(v, "uploads/")

    @field_validator("image_thumbnail")
    @classmethod
    def validate_image_thumbnail(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_safe_path(v, "thumbnails/")


class SaveResponseData(BaseModel):
    id: UUID
    created_at: datetime


class SaveResponse(BaseModel):
    success: bool = True
    data: SaveResponseData
