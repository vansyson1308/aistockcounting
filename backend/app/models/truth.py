import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_key: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    branch_code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    pos_branch_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now())


class Tray(Base):
    __tablename__ = "trays"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_key: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    branch_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tray_code: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(80), nullable=True)
    expected_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now())


class CatalogItem(Base):
    __tablename__ = "catalog_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_key: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    unit_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    pos_product_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now())


class PosInventorySnapshot(Base):
    __tablename__ = "pos_inventory_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_key: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    branch_code: Mapped[str] = mapped_column(String(80), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tray_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    expected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="manual")
    source_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now())


class ScanSession(Base):
    __tablename__ = "scan_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_key: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    branch_code: Mapped[str] = mapped_column(String(80), nullable=False)
    tray_code: Mapped[str] = mapped_column(String(80), nullable=False)
    staff_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    image_thumbnail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    detected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    manual_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    variance_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    variance_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    boxes_json: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_flags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    is_ai_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending_review")
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(), server_default=func.now(), onupdate=func.now()
    )


class Discrepancy(Base):
    __tablename__ = "discrepancies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    tenant_key: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    branch_code: Mapped[str] = mapped_column(String(80), nullable=False)
    tray_code: Mapped[str] = mapped_column(String(80), nullable=False)
    expected_count: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_count: Mapped[int] = mapped_column(Integer, nullable=False)
    variance_count: Mapped[int] = mapped_column(Integer, nullable=False)
    variance_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_key: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    actor_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now())


class PosSyncEvent(Base):
    __tablename__ = "pos_sync_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_key: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="kiotviet")
    event_key: Mapped[str] = mapped_column(String(160), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="processed")
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now())
