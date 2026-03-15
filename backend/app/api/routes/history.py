from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_key, get_cached, set_cached
from app.core.errors import api_error
from app.db.database import get_db
from app.models.count import Count
from app.schemas.history import HistoryResponse, HistorySingleResponse

router = APIRouter(prefix="", tags=["Records"])


@router.get(
    "/history",
    response_model=HistoryResponse,
    summary="List count history with filters",
)
async def get_history(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    staff_id: str | None = Query(default=None),
    tray_id: str | None = Query(default=None),
    ai_correct: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse | HistoryResponse:
    ck = cache_key(
        "history",
        str(page),
        str(limit),
        str(date_from),
        str(date_to),
        str(staff_id),
        str(tray_id),
        str(ai_correct),
    )
    cached = get_cached(ck)
    if cached is not None:
        return JSONResponse(content=cached, headers={"X-Cache": "HIT"})

    q = select(Count)
    cq = select(func.count(Count.id))

    if date_from:
        q = q.where(Count.created_at >= date_from)
        cq = cq.where(Count.created_at >= date_from)
    if date_to:
        q = q.where(Count.created_at <= date_to)
        cq = cq.where(Count.created_at <= date_to)
    if staff_id:
        q = q.where(Count.staff_id == staff_id)
        cq = cq.where(Count.staff_id == staff_id)
    if tray_id:
        q = q.where(Count.tray_id == tray_id)
        cq = cq.where(Count.tray_id == tray_id)
    if ai_correct is not None:
        q = q.where(Count.is_ai_correct == ai_correct)
        cq = cq.where(Count.is_ai_correct == ai_correct)

    total = (await db.execute(cq)).scalar_one()
    rows = (
        await db.execute(
            q.order_by(Count.created_at.desc()).offset((page - 1) * limit).limit(limit)
        )
    ).scalars()

    items = [
        {
            "id": row.id,
            "image_path": row.image_path,
            "image_thumbnail": row.image_thumbnail,
            "detected_count": row.detected_count,
            "manual_count": row.manual_count,
            "confidence_avg": row.confidence_avg,
            "staff_id": row.staff_id,
            "tray_id": row.tray_id,
            "is_ai_correct": row.is_ai_correct,
            "notes": row.notes,
            "boxes_json": row.boxes_json,
            "created_at": row.created_at,
        }
        for row in rows
    ]
    result = HistoryResponse(
        data={"items": items, "page": page, "limit": limit, "total": total}
    )
    body = result.model_dump(mode="json")
    set_cached(ck, body, ttl=120)
    return JSONResponse(content=body, headers={"X-Cache": "MISS"})


@router.get(
    "/history/{record_id}",
    response_model=HistorySingleResponse,
    summary="Get record detail",
)
async def get_history_item(
    record_id: UUID, db: AsyncSession = Depends(get_db)
) -> HistorySingleResponse:
    row = (
        await db.execute(select(Count).where(Count.id == record_id).limit(1))
    ).scalar_one_or_none()
    if row is None:
        raise api_error(404, "NOT_FOUND", "Record not found")

    return HistorySingleResponse(
        data={
            "id": row.id,
            "image_path": row.image_path,
            "image_thumbnail": row.image_thumbnail,
            "detected_count": row.detected_count,
            "manual_count": row.manual_count,
            "confidence_avg": row.confidence_avg,
            "staff_id": row.staff_id,
            "tray_id": row.tray_id,
            "is_ai_correct": row.is_ai_correct,
            "notes": row.notes,
            "boxes_json": row.boxes_json,
            "created_at": row.created_at,
        }
    )
