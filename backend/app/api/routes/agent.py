"""TrayAgent routes: run the agent, read its trace, and the human approval gate."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import progress
from app.agent.service import agent_payload, mark_approved, run_for_scan
from app.api.routes.truth import (
    _discrepancy_payload,
    _record_event,
    _scan_payload,
    _upsert_discrepancy,
    tenant_key,
)
from app.core.cache import invalidate
from app.core.config import get_settings
from app.core.errors import api_error
from app.db.database import get_db
from app.models.agent import AgentStep
from app.models.truth import AuditEvent, Discrepancy, ScanSession
from app.schemas.agent import (
    AgentRunResponse,
    ApproveRequest,
    ApproveResponse,
    TraceResponse,
)
from app.services.inference import InferenceService
from app.services.storage import StorageService

router = APIRouter(prefix="", tags=["Agent"])

# Statuses the agent may (re-)run from. It may never run over a pending human
# decision or over a human's final decision (approved_by, or a human review;
# see _human_reviewed).
RUNNABLE = {"pending_review", "needs_recapture", "agent_running", "discrepancy_open"}


async def _load_scan(db: AsyncSession, scan_id: UUID, tenant: str) -> ScanSession:
    scan = (
        await db.execute(
            select(ScanSession).where(
                ScanSession.id == scan_id, ScanSession.tenant_key == tenant
            )
        )
    ).scalar_one_or_none()
    if scan is None:
        raise api_error(404, "SCAN_NOT_FOUND", "Scan not found")
    return scan


async def _open_discrepancy(db: AsyncSession, scan_id: UUID) -> Discrepancy | None:
    return (
        await db.execute(
            select(Discrepancy)
            .where(Discrepancy.scan_id == scan_id, Discrepancy.status == "open")
            .limit(1)
        )
    ).scalar_one_or_none()


async def _human_reviewed(db: AsyncSession, scan: ScanSession) -> bool:
    """True once a human entered a count through PATCH /review.

    That review can leave the scan in ``discrepancy_open``, a status the agent
    may otherwise run from (legacy single-shot scans), so the status alone
    does not tell whether the count is a human's final decision.
    """
    if scan.manual_count is not None:
        return True
    reviewed = (
        await db.execute(
            select(AuditEvent.id)
            .where(
                AuditEvent.tenant_key == scan.tenant_key,
                AuditEvent.entity_type == "scan_session",
                AuditEvent.entity_id == str(scan.id),
                AuditEvent.action == "SCAN_REVIEWED",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return reviewed is not None


def evidence_url(key: str | None) -> str | None:
    if not key:
        return None
    return f"{get_settings().api_prefix}/images/object/{key}"


@router.post(
    "/scans/{scan_id}/agent-run",
    response_model=AgentRunResponse,
    summary="Run TrayAgent on a stored scan",
)
async def agent_run(
    scan_id: UUID,
    tenant: str = Depends(tenant_key),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(StorageService),
    inference: InferenceService = Depends(InferenceService),
) -> AgentRunResponse:
    scan = await _load_scan(db, scan_id, tenant)
    if (
        scan.status not in RUNNABLE
        or scan.approved_by is not None
        or await _human_reviewed(db, scan)
    ):
        raise api_error(
            409,
            "AGENT_RUN_NOT_ALLOWED",
            f"Scan status '{scan.status}' cannot be re-run by the agent.",
        )
    result = await run_for_scan(
        db,
        scan,
        detector=inference.detector(),
        storage=storage,
        unit_value=scan.unit_value,
    )
    await db.commit()
    await db.refresh(scan)
    discrepancy = await _open_discrepancy(db, scan.id)
    invalidate()
    return AgentRunResponse(
        data={
            "scan": _scan_payload(scan),
            "discrepancy": _discrepancy_payload(discrepancy) if discrepancy else None,
            "agent": agent_payload(scan, result),
        }
    )


@router.get(
    "/scans/{scan_id}/trace",
    response_model=TraceResponse,
    summary="Agent trace: every tool call, decision, reason, latency and evidence",
)
async def get_trace(
    scan_id: UUID,
    tenant: str = Depends(tenant_key),
    db: AsyncSession = Depends(get_db),
) -> TraceResponse:
    scan = await _load_scan(db, scan_id, tenant)
    rows = (
        await db.execute(
            select(AgentStep)
            .where(AgentStep.scan_id == scan.id, AgentStep.tenant_key == tenant)
            .order_by(desc(AgentStep.created_at), AgentStep.seq)
        )
    ).scalars()
    runs: dict[str, list[dict]] = {}
    for r in rows:
        runs.setdefault(str(r.run_id), []).append(
            {
                "seq": r.seq,
                "step_no": r.step_no,
                "tool": r.tool,
                "inputs": r.inputs_json,
                "outputs": r.outputs_json,
                "evidence_key": r.evidence_key,
                "evidence_url": evidence_url(r.evidence_key),
                "decision": r.decision,
                "reason": r.reason,
                "latency_ms": r.latency_ms,
                "planner": r.planner,
            }
        )
    for steps in runs.values():
        steps.sort(key=lambda x: x["seq"])
    live = progress.get(str(scan.id))
    if live is not None:
        live = {
            **live,
            "steps": [
                {**s, "evidence_url": evidence_url(s.get("evidence_key"))}
                for s in live["steps"]
            ],
        }
    latest = str(scan.agent_run_id) if scan.agent_run_id else None
    return TraceResponse(
        data={
            "scan": _scan_payload(scan),
            "latest_run_id": latest,
            "steps": runs.get(latest, []) if latest else [],
            "runs": [{"run_id": k, "steps": v} for k, v in runs.items()],
            "live": live,
        }
    )


@router.post(
    "/scans/{scan_id}/approve",
    response_model=ApproveResponse,
    summary="Human approval gate: approve, correct or reject an escalated count",
)
async def approve_scan(
    scan_id: UUID,
    payload: ApproveRequest,
    tenant: str = Depends(tenant_key),
    db: AsyncSession = Depends(get_db),
) -> ApproveResponse:
    scan = await _load_scan(db, scan_id, tenant)
    if scan.status != "awaiting_approval":
        raise api_error(
            409,
            "NOT_AWAITING_APPROVAL",
            f"Scan status is '{scan.status}'; only escalated scans can be approved.",
        )
    if payload.decision == "approve" and scan.agent_count is None:
        # The agent escalated before it produced a count (e.g. the planner
        # escalated right after assess, or the budget ran out): there is no
        # agent count to approve, and approving must never record a stale or
        # default number.
        raise api_error(
            409,
            "NO_AGENT_COUNT",
            "The agent produced no count for this scan; correct it or reject it.",
        )
    before = {"agent_count": scan.agent_count, "final_count": scan.final_count}
    if payload.decision == "reject":
        scan.status = "needs_recapture"
        scan.notes = payload.note
        mark_approved(scan, payload.approver_id)
        discrepancy = await _open_discrepancy(db, scan.id)
        if discrepancy is not None:
            discrepancy.status = "ignored"
            discrepancy.resolution_note = (
                "Agent count rejected by a human; recount required."
            )
            discrepancy.resolved_by = payload.approver_id
    else:
        count = (
            payload.corrected_count
            if payload.decision == "correct"
            else scan.agent_count
        )
        scan.final_count = int(count)
        if payload.decision == "correct":
            scan.manual_count = int(count)
            scan.is_ai_correct = count == scan.agent_count
        else:
            scan.is_ai_correct = True
        scan.notes = payload.note
        scan.variance_count = (
            scan.final_count - scan.expected_count
            if scan.expected_count is not None
            else None
        )
        mark_approved(scan, payload.approver_id)
        if scan.expected_count is None:
            scan.status = "reviewed"
            discrepancy = None
        else:
            # Truth workflow: variance 0 -> reviewed; otherwise the confirmed
            # variance stays open in the discrepancy inbox for resolution.
            discrepancy = await _upsert_discrepancy(
                db, scan, unit_value=payload.unit_value
            )
    await _record_event(
        db,
        tenant=tenant,
        actor_id=payload.approver_id,
        action="SCAN_APPROVAL",
        entity_type="scan_session",
        entity_id=str(scan.id),
        payload={
            "decision": payload.decision,
            "before": before,
            "final_count": scan.final_count,
            "status": scan.status,
            "note": payload.note,
            "agent_run_id": str(scan.agent_run_id) if scan.agent_run_id else None,
        },
    )
    await db.commit()
    await db.refresh(scan)
    if discrepancy is not None:
        await db.refresh(discrepancy)
    invalidate()
    return ApproveResponse(
        data={
            "scan": _scan_payload(scan),
            "discrepancy": _discrepancy_payload(discrepancy) if discrepancy else None,
        }
    )
