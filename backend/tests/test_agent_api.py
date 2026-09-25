"""API tests for TrayAgent: POST /scans (agent on), agent-run, trace, and the approval gate."""

import uuid

import pytest
from sqlalchemy import select

from app.services.detector_cv import ClassicalDetector, DetectorStatus
from app.services.inference import InferenceService
from tests.fixtures.synth_tray import make_tray


@pytest.fixture
def agent_on(monkeypatch):
    """Agent enabled, the classical OpenCV detector, and in-memory object storage."""
    from app.core.config import get_settings
    from app.services.storage import StorageService

    settings = get_settings()
    monkeypatch.setattr(settings, "agent_enabled", True)
    objects: dict[str, bytes] = {}

    def save(self, payload, name):
        key = f"uploads/{uuid.uuid4().hex}.jpg"
        objects[key] = payload
        return key, None

    def put_bytes(self, key, body, content_type="image/jpeg"):
        objects[key] = body
        return key

    def get_object_stream(self, key):
        import io

        return io.BytesIO(objects[key]), "image/jpeg"

    monkeypatch.setattr(StorageService, "save_image_and_thumbnail", save)
    monkeypatch.setattr(StorageService, "put_bytes", put_bytes)
    monkeypatch.setattr(StorageService, "get_bytes", lambda self, key: objects[key])
    monkeypatch.setattr(StorageService, "get_object_stream", get_object_stream)
    InferenceService.set_detector(
        ClassicalDetector(), DetectorStatus("classical", True)
    )
    yield objects
    InferenceService.reset()


async def _scan(client, tray, *, expected=None, tray_code="T-A", **extra):
    data = {
        "branch_code": "HN-01",
        "tray_code": tray_code,
        "staff_id": "EMP-1",
        **extra,
    }
    if expected is not None:
        data["expected_count"] = str(expected)
    res = await client.post(
        "/api/v1/scans",
        files={"image": ("tray.jpg", tray.jpeg(), "image/jpeg")},
        data=data,
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def test_clean_tray_auto_accepts_and_trace_is_persisted(client, agent_on) -> None:
    body = await _scan(client, make_tray(n_items=12, seed=11), expected=12)
    scan, agent = body["scan"], body["agent"]
    assert agent["decision"] == "auto_accept"
    assert scan["status"] == "reviewed" and scan["final_count"] == 12
    assert scan["agent_count"] == 12 and scan["variance_count"] == 0
    assert body["discrepancy"] is None
    assert len(scan["boxes_json"]) == 12

    trace = (await client.get(f"/api/v1/scans/{scan['id']}/trace")).json()["data"]
    tools = [s["tool"] for s in trace["steps"]]
    assert tools == ["assess_quality", "rectify_tray", "detect", "render_evidence"]
    assert all(
        s["evidence_url"].startswith("/api/v1/images/object/evidence/")
        for s in trace["steps"]
    )
    assert trace["live"]["running"] is False
    # evidence images are served by the existing proxy
    img = await client.get(trace["steps"][0]["evidence_url"])
    assert img.status_code == 200 and img.content[:3] == b"\xff\xd8\xff"


async def test_audit_events_per_decision(client, agent_on) -> None:
    from app.db.database import get_db
    from app.main import app
    from app.models.agent import AgentStep
    from app.models.truth import AuditEvent

    body = await _scan(client, make_tray(n_items=12, seed=11), expected=12)
    override = app.dependency_overrides[get_db]
    async for db in override():
        steps = (await db.execute(select(AgentStep))).scalars().all()
        events = (await db.execute(select(AuditEvent))).scalars().all()
    assert len(steps) == 4
    actions = [e.action for e in events]
    assert actions.count("AGENT_DECISION") == 3  # assess, count, auto_accept
    assert "AGENT_RUN_COMPLETED" in actions and "SCAN_CREATED" in actions
    assert all(str(s.scan_id) == body["scan"]["id"] for s in steps)


async def test_glare_needs_recapture_then_reshot_is_linked(client, agent_on) -> None:
    first = await _scan(
        client, make_tray(n_items=12, seed=12, glare=0.2), expected=12, tray_code="T-B"
    )
    assert first["scan"]["status"] == "needs_recapture"
    assert "Tilt the phone" in first["agent"]["instruction"]
    second = await _scan(
        client,
        make_tray(n_items=12, seed=12),
        expected=12,
        tray_code="T-B",
        parent_scan_id=first["scan"]["id"],
    )
    assert second["scan"]["attempt"] == 1
    assert second["scan"]["parent_scan_id"] == first["scan"]["id"]
    assert second["agent"]["decision"] == "auto_accept"
    parent = (await client.get(f"/api/v1/scans/{first['scan']['id']}/trace")).json()[
        "data"
    ]
    assert parent["scan"]["status"] == "superseded"


async def _tray_c(client):
    prev = make_tray(n_items=40, item_radius=(12, 16), seed=21)
    curr = make_tray(
        n_items=40, item_radius=(12, 16), seed=21, exclude_items=[7], perspective=0.05
    )
    yesterday = await _scan(client, prev, expected=40, tray_code="T-C")
    assert yesterday["scan"]["status"] == "reviewed"
    return await _scan(client, curr, expected=40, tray_code="T-C", unit_value="2500000")


async def test_mismatch_compares_with_yesterday_and_escalates(client, agent_on) -> None:
    body = await _tray_c(client)
    scan, agent = body["scan"], body["agent"]
    assert agent["decision"] == "escalate"
    assert scan["status"] == "awaiting_approval"
    assert "compare_previous" in [s["tool"] for s in agent["trace"]]
    assert agent["changed_regions"]
    assert body["discrepancy"]["status"] == "open"
    assert body["discrepancy"]["variance_count"] == -1


async def test_approval_gate_cannot_be_bypassed(client, agent_on) -> None:
    body = await _tray_c(client)
    sid, did = body["scan"]["id"], body["discrepancy"]["id"]

    r = await client.patch(f"/api/v1/scans/{sid}/review", json={"manual_count": 40})
    assert r.status_code == 409 and r.json()["error"]["code"] == "APPROVAL_REQUIRED"
    r = await client.post(
        f"/api/v1/discrepancies/{did}/resolve",
        json={"status": "resolved", "resolution_note": "x", "resolved_by": "M"},
    )
    assert r.status_code == 409
    r = await client.post(f"/api/v1/scans/{sid}/agent-run")
    assert r.status_code == 409 and r.json()["error"]["code"] == "AGENT_RUN_NOT_ALLOWED"
    r = await client.post(f"/api/v1/scans/{sid}/approve", json={"decision": "approve"})
    assert r.status_code == 422  # approver id is mandatory
    r = await client.post(
        f"/api/v1/scans/{sid}/approve",
        json={"approver_id": "MGR-1", "decision": "correct"},
    )
    assert r.status_code == 422  # a correction needs a count

    ok = await client.post(
        f"/api/v1/scans/{sid}/approve",
        json={
            "approver_id": "MGR-1",
            "decision": "approve",
            "note": "ring sold, POS late",
        },
    )
    assert ok.status_code == 200
    scan = ok.json()["data"]["scan"]
    assert scan["approved_by"] == "MGR-1" and scan["approved_at"]
    assert scan["final_count"] == 39
    assert scan["status"] == "discrepancy_open"  # confirmed variance goes to the inbox

    again = await client.post(
        f"/api/v1/scans/{sid}/approve",
        json={"approver_id": "MGR-1", "decision": "approve"},
    )
    assert again.status_code == 409
    rerun = await client.post(f"/api/v1/scans/{sid}/agent-run")
    assert rerun.status_code == 409


async def test_correct_to_pos_count_resolves(client, agent_on) -> None:
    body = await _tray_c(client)
    sid = body["scan"]["id"]
    r = await client.post(
        f"/api/v1/scans/{sid}/approve",
        json={"approver_id": "MGR-2", "decision": "correct", "corrected_count": 40},
    )
    scan = r.json()["data"]["scan"]
    assert scan["status"] == "reviewed" and scan["final_count"] == 40
    assert scan["manual_count"] == 40 and scan["is_ai_correct"] is False


async def test_reject_requires_recount(client, agent_on) -> None:
    body = await _tray_c(client)
    r = await client.post(
        f"/api/v1/scans/{body['scan']['id']}/approve",
        json={
            "approver_id": "MGR-3",
            "decision": "reject",
            "note": "photo of wrong tray",
        },
    )
    assert r.json()["data"]["scan"]["status"] == "needs_recapture"
    open_items = (await client.get("/api/v1/discrepancies")).json()["data"]["items"]
    assert all(d["scan_id"] != body["scan"]["id"] for d in open_items)


async def test_approve_rejects_non_escalated_scan(client, agent_on) -> None:
    body = await _scan(client, make_tray(n_items=12, seed=11), expected=12)
    r = await client.post(
        f"/api/v1/scans/{body['scan']['id']}/approve",
        json={"approver_id": "MGR-1", "decision": "approve"},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_AWAITING_APPROVAL"


async def test_agent_cannot_rerun_a_reviewed_scan(client, agent_on) -> None:
    body = await _scan(
        client, make_tray(n_items=12, seed=11), expected=12, run_agent="false"
    )
    assert body["agent"] is None  # legacy single-shot path
    assert body["scan"]["status"] == "reviewed"
    r = await client.post(f"/api/v1/scans/{body['scan']['id']}/agent-run")
    assert r.status_code == 409


async def test_agent_run_on_pending_scan(client, agent_on) -> None:
    body = await _scan(client, make_tray(n_items=12, seed=11), run_agent="false")
    sid = body["scan"]["id"]
    assert body["scan"]["status"] == "pending_review"
    r = await client.post(f"/api/v1/scans/{sid}/agent-run")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["agent"]["decision"] == "auto_accept"
    assert (
        data["scan"]["status"] == "pending_review"
    )  # no POS figure: nothing reconciled
    assert data["scan"]["agent_count"] == 12


async def test_trace_and_run_404(client, agent_on) -> None:
    missing = uuid.uuid4()
    assert (await client.get(f"/api/v1/scans/{missing}/trace")).status_code == 404
    assert (await client.post(f"/api/v1/scans/{missing}/agent-run")).status_code == 404
    r = await client.post(
        f"/api/v1/scans/{missing}/approve",
        json={"approver_id": "a", "decision": "approve"},
    )
    assert r.status_code == 404


async def test_parent_scan_must_exist(client, agent_on) -> None:
    res = await client.post(
        "/api/v1/scans",
        files={"image": ("tray.jpg", make_tray().jpeg(), "image/jpeg")},
        data={
            "branch_code": "B",
            "tray_code": "T",
            "parent_scan_id": str(uuid.uuid4()),
        },
    )
    assert res.status_code == 404


async def test_tenant_isolation_of_trace(client, agent_on) -> None:
    body = await _scan(client, make_tray(n_items=12, seed=11), expected=12)
    r = await client.get(
        f"/api/v1/scans/{body['scan']['id']}/trace", headers={"X-TENANT-KEY": "other"}
    )
    assert r.status_code == 404
