"""Run TrayAgent for a stored scan and apply the outcome to the truth layer.

This builds on the existing truth workflow (``_upsert_discrepancy``,
``_record_event`` and the ``ScanSession`` statuses) and adds two statuses:

* ``needs_recapture``: the agent asked for a re-shot (no count recorded);
* ``awaiting_approval``: the agent escalated. Only ``POST /scans/{id}/approve``
  moves the scan on. Re-runs, reviews and discrepancy resolution are refused
  while it waits (the approval gate).

``auto_accept`` never changes inventory: it is only allowed when the count
equals the POS figure (variance 0), or when there is no POS figure, in which
case the scan stays ``pending_review``.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

import numpy as np
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import progress
from app.agent.cloudwatch import publish
from app.agent.controller import AgentResult, EvidenceStore, run_agent
from app.agent.planner import build_planner
from app.agent.policy import Action, PolicyConfig
from app.agent.trace import persist_run
from app.core.config import get_settings
from app.core.metrics import agent_latency_seconds, agent_runs_total, agent_steps_used
from app.cv.imageio import decode_image
from app.models.truth import ScanSession
from app.services.detector_cv import Detector
from app.services.storage import StorageService

logger = logging.getLogger("app")

GATED_STATUSES = {"awaiting_approval"}


class S3EvidenceStore:
    def __init__(self, storage: StorageService) -> None:
        self.storage = storage

    def put(self, key: str, data: bytes) -> str:
        return self.storage.put_bytes(key, data, "image/jpeg")


async def previous_approved_scan(
    db: AsyncSession, scan: ScanSession
) -> ScanSession | None:
    """The latest earlier scan of the same tray that a human approved or that
    auto-accepted against POS: 'yesterday's approved photo'."""
    q = (
        select(ScanSession)
        .where(
            ScanSession.tenant_key == scan.tenant_key,
            ScanSession.tray_code == scan.tray_code,
            ScanSession.id != scan.id,
            or_(ScanSession.status == "reviewed", ScanSession.approved_by.is_not(None)),
        )
        .order_by(desc(ScanSession.created_at))
        .limit(1)
    )
    if scan.created_at is not None:
        q = q.where(ScanSession.created_at <= scan.created_at)
    return (await db.execute(q)).scalar_one_or_none()


def policy_from_settings() -> PolicyConfig:
    s = get_settings()
    return PolicyConfig(
        max_steps=s.agent_max_steps, time_budget_s=s.agent_time_budget_s
    )


async def run_for_scan(
    db: AsyncSession,
    scan: ScanSession,
    *,
    detector: Detector,
    storage: StorageService,
    image_bytes: bytes | None = None,
    unit_value: float | None = None,
    evidence: EvidenceStore | None = None,
) -> AgentResult:
    from app.api.routes.truth import _record_event, _upsert_discrepancy

    settings = get_settings()
    payload = image_bytes
    if payload is None:
        payload = await asyncio.to_thread(storage.get_bytes, scan.image_path)
    image = decode_image(payload)

    previous = await previous_approved_scan(db, scan)
    prev_img: np.ndarray | None = None
    if previous is not None:
        try:
            prev_img = decode_image(
                await asyncio.to_thread(storage.get_bytes, previous.image_path)
            )
        except Exception:
            logger.warning(
                "previous approved image unavailable for %s", previous.id, exc_info=True
            )

    run_id = uuid.uuid4()
    scan_key = str(scan.id)
    progress.start(scan_key, str(run_id))
    try:
        result = await asyncio.to_thread(
            run_agent,
            image,
            detector=detector,
            expected_count=scan.expected_count,
            previous_image=prev_img,
            previous_ref=(
                str(previous.id)
                if previous is not None and prev_img is not None
                else None
            ),
            attempt=scan.attempt or 0,
            cfg=policy_from_settings(),
            planner=build_planner(settings),
            evidence=evidence or S3EvidenceStore(storage),
            key_prefix=f"evidence/{scan.id.hex}/{run_id.hex}",
            run_id=run_id,
            on_step=lambda e: progress.add_step(scan_key, e.as_dict()),
        )
    finally:
        progress.finish(scan_key)

    apply_result(scan, result)
    if result.action == Action.REQUEST_RECAPTURE:
        scan.status = "needs_recapture"
    elif result.action == Action.AUTO_ACCEPT:
        if scan.expected_count is not None:
            await _upsert_discrepancy(
                db, scan, unit_value=unit_value
            )  # variance 0 -> reviewed
        else:
            scan.status = "pending_review"
    else:
        await _upsert_discrepancy(db, scan, unit_value=unit_value)
        scan.status = "awaiting_approval"

    persist_run(
        db, result, scan_id=scan.id, tenant=scan.tenant_key, actor_id=scan.staff_id
    )
    await _record_event(
        db,
        tenant=scan.tenant_key,
        actor_id=scan.staff_id,
        action="SCAN_AGENT_RUN",
        entity_type="scan_session",
        entity_id=str(scan.id),
        payload={
            "run_id": str(run_id),
            "decision": result.action.value,
            "status": scan.status,
        },
    )
    summary = result.summary()
    agent_runs_total.labels(result.action.value, result.code, result.planner).inc()
    agent_steps_used.observe(result.steps_used)
    agent_latency_seconds.observe(result.elapsed_ms / 1000)
    if settings.cloudwatch_metrics_enabled:
        publish(summary, settings.cloudwatch_namespace, settings.aws_region)
    logger.info("agent_run", extra={"agent": summary})
    return result


def apply_result(scan: ScanSession, result: AgentResult) -> None:
    scan.agent_run_id = result.run_id
    scan.agent_decision = result.action.value
    scan.agent_reason = result.reason[:2000]
    scan.agent_count = result.count
    quality = next(
        (e.outputs for e in result.trace if e.tool == "assess_quality"), None
    )
    if quality is not None:
        scan.quality_score = quality.get("score")
        scan.quality_flags = quality.get("flags")
    if result.count is None:
        return
    boxes = [d.as_dict() for d in result.dets_original]
    scan.detected_count = result.count
    scan.final_count = result.count
    scan.boxes_json = boxes
    scan.confidence_avg = (
        round(sum(b["conf"] for b in boxes) / len(boxes), 4) if boxes else 0.0
    )
    scan.processing_time_ms = result.elapsed_ms
    if scan.expected_count is not None:
        scan.variance_count = result.count - scan.expected_count


def agent_payload(
    scan: ScanSession, result: AgentResult | None
) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        **result.summary(),
        "status": scan.status,
        "trace": [e.as_dict() for e in result.trace],
    }


def mark_approved(scan: ScanSession, approver: str) -> None:
    scan.approved_by = approver
    scan.approved_at = datetime.utcnow()
