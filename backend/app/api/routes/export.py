import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.count import Count

router = APIRouter(prefix="", tags=["Analytics"])

_CSV_COLUMNS = [
    "id",
    "image_path",
    "detected_count",
    "manual_count",
    "confidence_avg",
    "staff_id",
    "tray_id",
    "is_ai_correct",
    "notes",
    "model_version",
    "processing_time_ms",
    "created_at",
]


@router.get("/export/csv", summary="Export records as CSV")
async def export_csv(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    staff_id: str | None = Query(default=None),
    tray_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    q = select(Count)
    if date_from:
        q = q.where(Count.created_at >= date_from)
    if date_to:
        q = q.where(Count.created_at <= date_to)
    if staff_id:
        q = q.where(Count.staff_id == staff_id)
    if tray_id:
        q = q.where(Count.tray_id == tray_id)

    q = q.order_by(Count.created_at.desc())
    rows = (await db.execute(q)).scalars()

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(_CSV_COLUMNS)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

        for row in rows:
            writer.writerow([getattr(row, col) for col in _CSV_COLUMNS])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=stock_counts.csv"},
    )
