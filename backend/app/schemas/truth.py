from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.count import Box


class DiscrepancyData(BaseModel):
    id: UUID
    scan_id: UUID
    tenant_key: str
    branch_code: str
    tray_code: str
    expected_count: int
    actual_count: int
    variance_count: int
    variance_value: float | None = None
    severity: str
    status: str
    resolution_note: str | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime


class ScanSessionData(BaseModel):
    id: UUID
    tenant_key: str
    branch_code: str
    tray_code: str
    staff_id: str | None = None
    image_path: str
    image_thumbnail: str | None = None
    detected_count: int
    manual_count: int | None = None
    final_count: int
    expected_count: int | None = None
    variance_count: int | None = None
    variance_value: float | None = None
    confidence_avg: float | None = None
    boxes_json: list[Box] | None = None
    quality_score: float | None = None
    quality_flags: list[str] | None = None
    is_ai_correct: bool | None = None
    notes: str | None = None
    status: str
    model_version: str | None = None
    processing_time_ms: int | None = None
    created_at: datetime


class ScanCreateResponseData(BaseModel):
    scan: ScanSessionData
    discrepancy: DiscrepancyData | None = None


class ScanCreateResponse(BaseModel):
    success: bool = True
    data: ScanCreateResponseData


class ScanReviewRequest(BaseModel):
    manual_count: int | None = Field(default=None, ge=0)
    expected_count: int | None = Field(default=None, ge=0)
    unit_value: float | None = Field(default=None, ge=0)
    is_ai_correct: bool | None = None
    notes: str | None = Field(default=None, max_length=500)


class ScanReviewResponse(BaseModel):
    success: bool = True
    data: ScanCreateResponseData


class DiscrepancyListData(BaseModel):
    items: list[DiscrepancyData]
    total: int


class DiscrepancyListResponse(BaseModel):
    success: bool = True
    data: DiscrepancyListData


class DiscrepancyResolveRequest(BaseModel):
    status: str = Field(pattern="^(resolved|ignored)$")
    resolution_note: str = Field(min_length=1, max_length=500)
    resolved_by: str | None = Field(default=None, max_length=50)


class DiscrepancyResolveResponse(BaseModel):
    success: bool = True
    data: DiscrepancyData


class InventorySnapshotItem(BaseModel):
    branch_code: str = Field(max_length=80)
    sku: str | None = Field(default=None, max_length=80)
    tray_code: str | None = Field(default=None, max_length=80)
    product_name: str | None = Field(default=None, max_length=240)
    expected_count: int = Field(ge=0)
    unit_value: float | None = Field(default=None, ge=0)
    source_ref: str | None = Field(default=None, max_length=160)


class InventorySnapshotRequest(BaseModel):
    tenant_key: str = Field(default="default", max_length=80)
    items: list[InventorySnapshotItem]


class InventorySnapshotResponseData(BaseModel):
    imported: int


class InventorySnapshotResponse(BaseModel):
    success: bool = True
    data: InventorySnapshotResponseData


class KiotVietWebhookRequest(BaseModel):
    event_key: str = Field(max_length=160)
    event_type: str = Field(max_length=80)
    tenant_key: str = Field(default="default", max_length=80)
    payload: dict = Field(default_factory=dict)


class KiotVietWebhookResponseData(BaseModel):
    status: str
    duplicate: bool = False


class KiotVietWebhookResponse(BaseModel):
    success: bool = True
    data: KiotVietWebhookResponseData


class KiotVietStatusData(BaseModel):
    provider: str = "kiotviet"
    configured: bool
    snapshots: int
    last_sync_at: datetime | None = None
    last_event_at: datetime | None = None


class KiotVietStatusResponse(BaseModel):
    success: bool = True
    data: KiotVietStatusData


class ImageUrlResponse(BaseModel):
    success: bool = True
    data: dict[str, str]
