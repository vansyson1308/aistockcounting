from pydantic import BaseModel, Field


class Box(BaseModel):
    x: float
    y: float
    w: float
    h: float
    conf: float = Field(ge=0, le=1)


class CountResponseData(BaseModel):
    image_path: str
    image_thumbnail: str | None = None
    detected_count: int
    confidence_avg: float
    processing_time_ms: int
    boxes: list[Box]
    tray_id: str | None = None
    staff_id: str | None = None
    mock_mode: bool = False
    model_version: str = "unknown"


class CountResponse(BaseModel):
    success: bool = True
    data: CountResponseData
