from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.count import Count
from app.schemas.save import SaveRequest, SaveResponse

router = APIRouter(prefix="", tags=["Records"])


@router.post(
    "/save",
    response_model=SaveResponse,
    summary="Persist counted tray record",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": {
                        "image_path": "uploads/abc.jpg",
                        "image_thumbnail": "thumbnails/abc.jpg",
                        "detected_count": 12,
                        "manual_count": 11,
                        "confidence_avg": 0.81,
                        "boxes_json": [{"x": 10, "y": 20, "w": 30, "h": 40, "conf": 0.9}],
                        "staff_id": "EMP-001",
                        "tray_id": "TRAY-A1",
                        "is_ai_correct": False,
                        "notes": "Hidden item at corner"
                    }
                }
            }
        }
    },
)
async def save_count(payload: SaveRequest, db: AsyncSession = Depends(get_db)) -> SaveResponse:
    row = Count(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return SaveResponse(data={"id": row.id, "created_at": row.created_at})
