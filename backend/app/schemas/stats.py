from pydantic import BaseModel


class StatsResponseData(BaseModel):
    total_records: int
    avg_detected_count: float
    avg_manual_count: float
    ai_correct_rate: float


class StatsResponse(BaseModel):
    success: bool = True
    data: StatsResponseData
