import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy import UUID as SAUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Count(Base):
    __tablename__ = "counts"

    id: Mapped[uuid.UUID] = mapped_column(
        SAUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    image_thumbnail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    detected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    manual_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    boxes_json: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    staff_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tray_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_ai_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now()
    )
