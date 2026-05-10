import asyncio
import csv
import io
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit_log
from app.core.cache import invalidate
from app.core.config import get_settings
from app.core.errors import api_error
from app.db.database import get_db
from app.models.truth import (
    AuditEvent,
    Discrepancy,
    PosInventorySnapshot,
    PosSyncEvent,
    ScanSession,
    Tray,
)
from app.schemas.truth import (
    DiscrepancyListResponse,
    DiscrepancyResolveRequest,
    DiscrepancyResolveResponse,
    ImageUrlResponse,
    InventorySnapshotRequest,
    InventorySnapshotResponse,
    KiotVietStatusResponse,
    KiotVietWebhookRequest,
    KiotVietWebhookResponse,
    ScanCreateResponse,
    ScanReviewRequest,
    ScanReviewResponse,
)
from app.services.inference import InferenceService
from app.services.storage import StorageService
from app.utils.image_quality import assess_image_quality
from app.utils.image_validation import (
    validate_decodable_image,
    validate_file_size,
    validate_file_type,
)
from app.schemas.save import _validate_safe_path

router = APIRouter(prefix="", tags=["Inventory Truth"])


def tenant_key(x_tenant_key: str | None = Header(default=None, alias="X-TENANT-KEY")) -> str:
    return (x_tenant_key or get_settings().default_tenant_key).strip() or "default"


def _severity(variance_count: int, variance_value: float | None) -> str:
    money = abs(variance_value or 0)
    count = abs(variance_count)
    if count >= 5 or money >= 10_000_000:
        return "high"
    if count >= 2 or money >= 2_000_000:
        return "medium"
    return "low"


def _scan_payload(row: ScanSession) -> dict:
    return {
        "id": row.id,
        "tenant_key": row.tenant_key,
        "branch_code": row.branch_code,
        "tray_code": row.tray_code,
        "staff_id": row.staff_id,
        "image_path": row.image_path,
        "image_thumbnail": row.image_thumbnail,
        "detected_count": row.detected_count,
        "manual_count": row.manual_count,
        "final_count": row.final_count,
        "expected_count": row.expected_count,
        "variance_count": row.variance_count,
        "variance_value": row.variance_value,
        "confidence_avg": row.confidence_avg,
        "boxes_json": row.boxes_json or [],
        "quality_score": row.quality_score,
        "quality_flags": row.quality_flags or [],
        "is_ai_correct": row.is_ai_correct,
        "notes": row.notes,
        "status": row.status,
        "model_version": row.model_version,
        "processing_time_ms": row.processing_time_ms,
        "created_at": row.created_at,
    }


def _discrepancy_payload(row: Discrepancy) -> dict:
    return {
        "id": row.id,
        "scan_id": row.scan_id,
        "tenant_key": row.tenant_key,
        "branch_code": row.branch_code,
        "tray_code": row.tray_code,
        "expected_count": row.expected_count,
        "actual_count": row.actual_count,
        "variance_count": row.variance_count,
        "variance_value": row.variance_value,
        "severity": row.severity,
        "status": row.status,
        "resolution_note": row.resolution_note,
        "resolved_by": row.resolved_by,
        "resolved_at": row.resolved_at,
        "created_at": row.created_at,
    }


def _safe_object_key(path: str) -> str:
    allowed_prefix = "uploads/" if path.startswith("uploads/") else "thumbnails/"
    try:
        return _validate_safe_path(path, allowed_prefix)
    except ValueError as exc:
        raise api_error(400, "INVALID_IMAGE_PATH", str(exc)) from exc


async def _record_event(
    db: AsyncSession,
    *,
    tenant: str,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    payload: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            tenant_key=tenant,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=payload,
        )
    )


async def _expected_from_pos_or_tray(
    db: AsyncSession, *, tenant: str, branch_code: str, tray_code: str
) -> tuple[int | None, float | None]:
    snapshot = (
        await db.execute(
            select(PosInventorySnapshot)
            .where(
                PosInventorySnapshot.tenant_key == tenant,
                PosInventorySnapshot.branch_code == branch_code,
                PosInventorySnapshot.tray_code == tray_code,
            )
            .order_by(desc(PosInventorySnapshot.synced_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if snapshot is not None:
        return snapshot.expected_count, snapshot.unit_value

    tray = (
        await db.execute(
            select(Tray)
            .where(Tray.tenant_key == tenant, Tray.tray_code == tray_code)
            .order_by(desc(Tray.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if tray is not None:
        return tray.expected_count, tray.unit_value
    return None, None


async def _upsert_discrepancy(
    db: AsyncSession,
    scan: ScanSession,
    *,
    unit_value: float | None,
) -> Discrepancy | None:
    if scan.expected_count is None or scan.variance_count is None:
        return None

    existing = (
        await db.execute(
            select(Discrepancy)
            .where(Discrepancy.scan_id == scan.id, Discrepancy.status == "open")
            .limit(1)
        )
    ).scalar_one_or_none()

    if scan.variance_count == 0:
        scan.status = "reviewed"
        if existing is not None:
            existing.status = "resolved"
            existing.resolution_note = "Auto-resolved after count matched expected stock."
            existing.resolved_at = datetime.utcnow()
        return None

    variance_value = (
        float(scan.variance_count) * float(unit_value)
        if unit_value is not None
        else scan.variance_value
    )
    scan.variance_value = variance_value
    scan.status = "discrepancy_open"

    if existing is None:
        existing = Discrepancy(
            scan_id=scan.id,
            tenant_key=scan.tenant_key,
            branch_code=scan.branch_code,
            tray_code=scan.tray_code,
            expected_count=scan.expected_count,
            actual_count=scan.final_count,
            variance_count=scan.variance_count,
            variance_value=variance_value,
            severity=_severity(scan.variance_count, variance_value),
        )
        db.add(existing)
    else:
        existing.expected_count = scan.expected_count
        existing.actual_count = scan.final_count
        existing.variance_count = scan.variance_count
        existing.variance_value = variance_value
        existing.severity = _severity(scan.variance_count, variance_value)
    return existing


@router.post("/scans", response_model=ScanCreateResponse, summary="Create an audit scan")
async def create_scan(
    image: UploadFile = File(...),
    branch_code: str = Form(...),
    tray_code: str = Form(...),
    staff_id: str | None = Form(default=None),
    expected_count: int | None = Form(default=None),
    unit_value: float | None = Form(default=None),
    tenant: str = Depends(tenant_key),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(StorageService),
    inference: InferenceService = Depends(InferenceService),
) -> ScanCreateResponse:
    validate_file_type(image)
    payload = await image.read()
    validate_file_size(payload)
    validate_decodable_image(payload)

    image_path, image_thumbnail = await asyncio.to_thread(
        storage.save_image_and_thumbnail, payload, image.filename or "audit.jpg"
    )
    detection = await inference.predict(payload)
    quality = assess_image_quality(payload)

    fallback_expected, fallback_unit_value = await _expected_from_pos_or_tray(
        db, tenant=tenant, branch_code=branch_code, tray_code=tray_code
    )
    final_expected = expected_count if expected_count is not None else fallback_expected
    final_unit_value = unit_value if unit_value is not None else fallback_unit_value
    detected_count = int(detection["detected_count"])
    variance_count = (
        detected_count - final_expected if final_expected is not None else None
    )
    variance_value = (
        float(variance_count) * float(final_unit_value)
        if variance_count is not None and final_unit_value is not None
        else None
    )

    scan = ScanSession(
        tenant_key=tenant,
        branch_code=branch_code,
        tray_code=tray_code,
        staff_id=staff_id,
        image_path=image_path,
        image_thumbnail=image_thumbnail,
        detected_count=detected_count,
        final_count=detected_count,
        expected_count=final_expected,
        variance_count=variance_count,
        variance_value=variance_value,
        confidence_avg=detection.get("confidence_avg"),
        boxes_json=detection.get("boxes", []),
        quality_score=quality.score,
        quality_flags=quality.flags,
        status="pending_review",
        model_version=detection.get("model_version"),
        processing_time_ms=detection.get("processing_time_ms"),
    )
    db.add(scan)
    await db.flush()
    discrepancy = await _upsert_discrepancy(db, scan, unit_value=final_unit_value)
    await _record_event(
        db,
        tenant=tenant,
        actor_id=staff_id,
        action="SCAN_CREATED",
        entity_type="scan_session",
        entity_id=str(scan.id),
        payload={"quality_flags": quality.flags, "variance_count": variance_count},
    )
    await db.commit()
    await db.refresh(scan)
    if discrepancy is not None:
        await db.refresh(discrepancy)
    audit_log("SCAN_CREATED", staff_id, {"scan_id": str(scan.id)})
    invalidate()
    return ScanCreateResponse(
        data={
            "scan": _scan_payload(scan),
            "discrepancy": _discrepancy_payload(discrepancy) if discrepancy else None,
        }
    )


@router.patch(
    "/scans/{scan_id}/review",
    response_model=ScanReviewResponse,
    summary="Review an audit scan and update discrepancy state",
)
async def review_scan(
    scan_id: UUID,
    payload: ScanReviewRequest,
    tenant: str = Depends(tenant_key),
    db: AsyncSession = Depends(get_db),
) -> ScanReviewResponse:
    scan = (
        await db.execute(
            select(ScanSession).where(
                ScanSession.id == scan_id, ScanSession.tenant_key == tenant
            )
        )
    ).scalar_one_or_none()
    if scan is None:
        raise api_error(404, "SCAN_NOT_FOUND", "Scan not found")

    if payload.manual_count is not None:
        scan.manual_count = payload.manual_count
        scan.final_count = payload.manual_count
    else:
        scan.final_count = scan.detected_count
    if payload.expected_count is not None:
        scan.expected_count = payload.expected_count
    scan.is_ai_correct = payload.is_ai_correct
    scan.notes = payload.notes
    scan.variance_count = (
        scan.final_count - scan.expected_count if scan.expected_count is not None else None
    )
    scan.variance_value = (
        float(scan.variance_count) * float(payload.unit_value)
        if scan.variance_count is not None and payload.unit_value is not None
        else scan.variance_value
    )

    discrepancy = await _upsert_discrepancy(db, scan, unit_value=payload.unit_value)
    await _record_event(
        db,
        tenant=tenant,
        actor_id=scan.staff_id,
        action="SCAN_REVIEWED",
        entity_type="scan_session",
        entity_id=str(scan.id),
        payload={"manual_count": payload.manual_count, "variance_count": scan.variance_count},
    )
    await db.commit()
    await db.refresh(scan)
    if discrepancy is not None:
        await db.refresh(discrepancy)
    invalidate()
    return ScanReviewResponse(
        data={
            "scan": _scan_payload(scan),
            "discrepancy": _discrepancy_payload(discrepancy) if discrepancy else None,
        }
    )


@router.get(
    "/discrepancies",
    response_model=DiscrepancyListResponse,
    summary="List open or resolved stock discrepancies",
)
async def list_discrepancies(
    status: str = Query(default="open"),
    branch_code: str | None = Query(default=None),
    tenant: str = Depends(tenant_key),
    db: AsyncSession = Depends(get_db),
) -> DiscrepancyListResponse:
    q = select(Discrepancy).where(Discrepancy.tenant_key == tenant)
    cq = select(func.count(Discrepancy.id)).where(Discrepancy.tenant_key == tenant)
    if status:
        q = q.where(Discrepancy.status == status)
        cq = cq.where(Discrepancy.status == status)
    if branch_code:
        q = q.where(Discrepancy.branch_code == branch_code)
        cq = cq.where(Discrepancy.branch_code == branch_code)

    total = (await db.execute(cq)).scalar_one()
    rows = (
        await db.execute(q.order_by(desc(Discrepancy.created_at)).limit(100))
    ).scalars()
    return DiscrepancyListResponse(
        data={"items": [_discrepancy_payload(row) for row in rows], "total": total}
    )


@router.post(
    "/discrepancies/{discrepancy_id}/resolve",
    response_model=DiscrepancyResolveResponse,
    summary="Resolve or ignore a discrepancy",
)
async def resolve_discrepancy(
    discrepancy_id: UUID,
    payload: DiscrepancyResolveRequest,
    tenant: str = Depends(tenant_key),
    db: AsyncSession = Depends(get_db),
) -> DiscrepancyResolveResponse:
    discrepancy = (
        await db.execute(
            select(Discrepancy).where(
                Discrepancy.id == discrepancy_id, Discrepancy.tenant_key == tenant
            )
        )
    ).scalar_one_or_none()
    if discrepancy is None:
        raise api_error(404, "DISCREPANCY_NOT_FOUND", "Discrepancy not found")

    discrepancy.status = payload.status
    discrepancy.resolution_note = payload.resolution_note
    discrepancy.resolved_by = payload.resolved_by
    discrepancy.resolved_at = datetime.utcnow()
    scan = (
        await db.execute(select(ScanSession).where(ScanSession.id == discrepancy.scan_id))
    ).scalar_one_or_none()
    if scan is not None:
        scan.status = "reviewed" if payload.status == "resolved" else "ignored"

    await _record_event(
        db,
        tenant=tenant,
        actor_id=payload.resolved_by,
        action="DISCREPANCY_RESOLVED",
        entity_type="discrepancy",
        entity_id=str(discrepancy.id),
        payload={"status": payload.status},
    )
    await db.commit()
    await db.refresh(discrepancy)
    invalidate()
    return DiscrepancyResolveResponse(data=_discrepancy_payload(discrepancy))


@router.post(
    "/integrations/kiotviet/inventory-snapshots",
    response_model=InventorySnapshotResponse,
    summary="Import POS inventory snapshots from KiotViet or CSV fallback",
)
async def import_inventory_snapshots(
    payload: InventorySnapshotRequest,
    db: AsyncSession = Depends(get_db),
) -> InventorySnapshotResponse:
    for item in payload.items:
        db.add(
            PosInventorySnapshot(
                tenant_key=payload.tenant_key,
                branch_code=item.branch_code,
                sku=item.sku,
                tray_code=item.tray_code,
                product_name=item.product_name,
                expected_count=item.expected_count,
                unit_value=item.unit_value,
                source="kiotviet",
                source_ref=item.source_ref,
            )
        )
    await db.commit()
    invalidate()
    return InventorySnapshotResponse(data={"imported": len(payload.items)})


@router.post(
    "/integrations/kiotviet/csv",
    response_model=InventorySnapshotResponse,
    summary="Import inventory snapshots from a CSV export",
)
async def import_inventory_csv(
    file: UploadFile = File(...),
    tenant: str = Depends(tenant_key),
    db: AsyncSession = Depends(get_db),
) -> InventorySnapshotResponse:
    raw = await file.read()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    imported = 0
    for row in reader:
        branch_code = row.get("branch_code") or row.get("branch") or "MAIN"
        expected = row.get("expected_count") or row.get("quantity") or row.get("on_hand")
        if expected is None:
            continue
        unit_value_raw = row.get("unit_value") or row.get("price") or ""
        db.add(
            PosInventorySnapshot(
                tenant_key=tenant,
                branch_code=branch_code,
                sku=row.get("sku") or row.get("code") or None,
                tray_code=row.get("tray_code") or row.get("tray") or None,
                product_name=row.get("product_name") or row.get("name") or None,
                expected_count=int(float(expected)),
                unit_value=float(unit_value_raw) if unit_value_raw else None,
                source="csv",
                source_ref=file.filename,
            )
        )
        imported += 1
    await db.commit()
    invalidate()
    return InventorySnapshotResponse(data={"imported": imported})


@router.post(
    "/integrations/kiotviet/webhook",
    response_model=KiotVietWebhookResponse,
    summary="Record KiotViet webhook events with idempotency",
)
async def kiotviet_webhook(
    payload: KiotVietWebhookRequest, db: AsyncSession = Depends(get_db)
) -> KiotVietWebhookResponse:
    existing = (
        await db.execute(
            select(PosSyncEvent).where(
                PosSyncEvent.tenant_key == payload.tenant_key,
                PosSyncEvent.provider == "kiotviet",
                PosSyncEvent.event_key == payload.event_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return KiotVietWebhookResponse(
            data={"status": "already_processed", "duplicate": True}
        )

    db.add(
        PosSyncEvent(
            tenant_key=payload.tenant_key,
            provider="kiotviet",
            event_key=payload.event_key,
            event_type=payload.event_type,
            payload_json=payload.payload,
        )
    )
    await db.commit()
    invalidate()
    return KiotVietWebhookResponse(data={"status": "processed", "duplicate": False})


@router.get(
    "/integrations/kiotviet/status",
    response_model=KiotVietStatusResponse,
    summary="Show KiotViet connector status",
)
async def kiotviet_status(
    tenant: str = Depends(tenant_key), db: AsyncSession = Depends(get_db)
) -> KiotVietStatusResponse:
    settings = get_settings()
    snapshots, last_sync = (
        await db.execute(
            select(
                func.count(PosInventorySnapshot.id),
                func.max(PosInventorySnapshot.synced_at),
            ).where(PosInventorySnapshot.tenant_key == tenant)
        )
    ).one()
    last_event = (
        await db.execute(
            select(func.max(PosSyncEvent.created_at)).where(
                PosSyncEvent.tenant_key == tenant,
                PosSyncEvent.provider == "kiotviet",
            )
        )
    ).scalar_one()
    return KiotVietStatusResponse(
        data={
            "configured": bool(
                settings.kiotviet_client_id
                and settings.kiotviet_client_secret
                and settings.kiotviet_retailer
            ),
            "snapshots": int(snapshots),
            "last_sync_at": last_sync,
            "last_event_at": last_event,
        }
    )


@router.get(
    "/images/presigned",
    response_model=ImageUrlResponse,
    summary="Create a short-lived object URL for stored evidence images",
)
async def presigned_image_url(
    path: str = Query(...),
    storage: StorageService = Depends(StorageService),
) -> ImageUrlResponse:
    key = _safe_object_key(path)
    return ImageUrlResponse(data={"url": storage.presign_get_url(key)})


@router.get(
    "/images/object/{path:path}",
    summary="Proxy stored evidence images for the PWA",
)
async def proxy_image_object(
    path: str,
    storage: StorageService = Depends(StorageService),
) -> StreamingResponse:
    key = _safe_object_key(path)
    body, content_type = storage.get_object_stream(key)
    return StreamingResponse(body, media_type=content_type)
