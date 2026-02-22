from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.count import Box


class HistoryItem(BaseModel):
    id: UUID
    image_path: str
    image_thumbnail: str | None
    detected_count: int
    manual_count: int | None
    confidence_avg: float | None
    staff_id: str | None
    tray_id: str | None
    is_ai_correct: bool | None
    notes: str | None
    boxes_json: list[Box] | None
    created_at: datetime


class HistoryResponseData(BaseModel):
    items: list[HistoryItem]
    page: int
    limit: int
    total: int


class HistoryResponse(BaseModel):
    success: bool = True
    data: HistoryResponseData


class HistorySingleResponse(BaseModel):
    success: bool = True
    data: HistoryItem
