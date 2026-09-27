import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentStep(Base):
    """One tool call (or terminal action) of an agent run, as it happened."""

    __tablename__ = "agent_steps"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    scan_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    tenant_key: Mapped[str] = mapped_column(
        String(80), nullable=False, default="default"
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    tool: Mapped[str] = mapped_column(String(60), nullable=False)
    inputs_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    outputs_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decision: Mapped[str] = mapped_column(String(60), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    planner: Mapped[str] = mapped_column(
        String(20), nullable=False, default="deterministic"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now())
