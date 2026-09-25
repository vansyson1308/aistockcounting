"""Persist an agent run: one ``agent_steps`` row per tool call, plus an
``AuditEvent`` per decision and one for the run outcome.
"""

from __future__ import annotations

import uuid
from itertools import groupby

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.controller import AgentResult, TraceEntry
from app.models.agent import AgentStep
from app.models.truth import AuditEvent


def step_rows(
    result: AgentResult, *, scan_id: uuid.UUID, tenant: str
) -> list[AgentStep]:
    return [
        AgentStep(
            run_id=result.run_id,
            scan_id=scan_id,
            tenant_key=tenant,
            seq=e.seq,
            step_no=e.step_no,
            tool=e.tool,
            inputs_json=e.inputs,
            outputs_json=e.outputs,
            evidence_key=e.evidence_key,
            decision=e.decision,
            reason=e.reason,
            latency_ms=e.latency_ms,
            planner=e.planner,
        )
        for e in result.trace
    ]


def decision_events(
    result: AgentResult, *, scan_id: uuid.UUID, tenant: str, actor_id: str | None
) -> list[AuditEvent]:
    """One audit event per controller decision (grouped tool calls)."""
    events: list[AuditEvent] = []

    def key(e: TraceEntry) -> tuple[int, str]:
        return (e.step_no, e.decision)

    for (step_no, decision), group in groupby(result.trace, key=key):
        entries = list(group)
        events.append(
            AuditEvent(
                tenant_key=tenant,
                actor_id=actor_id,
                action="AGENT_DECISION",
                entity_type="scan_session",
                entity_id=str(scan_id),
                payload_json={
                    "run_id": str(result.run_id),
                    "step_no": step_no,
                    "decision": decision,
                    "reason": entries[0].reason,
                    "tools": [e.tool for e in entries],
                    "evidence_keys": [
                        e.evidence_key for e in entries if e.evidence_key
                    ],
                    "planner": entries[0].planner,
                },
            )
        )
    events.append(
        AuditEvent(
            tenant_key=tenant,
            actor_id=actor_id,
            action="AGENT_RUN_COMPLETED",
            entity_type="scan_session",
            entity_id=str(scan_id),
            payload_json=result.summary(),
        )
    )
    return events


def persist_run(
    db: AsyncSession,
    result: AgentResult,
    *,
    scan_id: uuid.UUID,
    tenant: str,
    actor_id: str | None,
) -> None:
    for row in step_rows(result, scan_id=scan_id, tenant=tenant):
        db.add(row)
    for ev in decision_events(
        result, scan_id=scan_id, tenant=tenant, actor_id=actor_id
    ):
        db.add(ev)
