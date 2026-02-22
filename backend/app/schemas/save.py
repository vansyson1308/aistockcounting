from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.count import Box


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
    notes: str | None = None


class SaveResponseData(BaseModel):
    id: UUID
    created_at: datetime


class SaveResponse(BaseModel):
    success: bool = True
    data: SaveResponseData
