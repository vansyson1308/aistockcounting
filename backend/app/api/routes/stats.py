from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.count import Count
from app.schemas.stats import StatsResponse

router = APIRouter(prefix="", tags=["Analytics"])


@router.get("/stats", response_model=StatsResponse, summary="Aggregate counting statistics")
async def get_stats(db: AsyncSession = Depends(get_db)) -> StatsResponse:
    query = select(
        func.count(Count.id),
        func.coalesce(func.avg(Count.detected_count), 0.0),
        func.coalesce(func.avg(Count.manual_count), 0.0),
        func.coalesce(func.avg(case((Count.is_ai_correct.is_(True), 1), else_=0)), 0.0),
    )
    total, avg_detected, avg_manual, ai_correct_rate = (await db.execute(query)).one()
    return StatsResponse(
        data={
            "total_records": int(total),
            "avg_detected_count": float(avg_detected),
            "avg_manual_count": float(avg_manual),
            "ai_correct_rate": float(ai_correct_rate),
        }
    )
