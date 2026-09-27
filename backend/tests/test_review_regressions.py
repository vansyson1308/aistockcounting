"""Regression tests for the post-merge review of the TrayAgent PR.

Each test pins one finding: the shared DNN net, the approval gate with no
agent count, rejected scans as references, re-runs over a human review, the
unit value in the deferred flow and after a correction, re-shots capped for
blur / framing, stale counts after a no-count run, and the stored image type.
"""

import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import select, update

from app.agent.policy import Action, Observation, PolicyConfig, decide
from tests.fixtures.synth_tray import make_tray
from tests import test_agent_api
from tests.test_agent_api import _scan, _tray_c

agent_on = test_agent_api.agent_on  # the fixture, shared with that module


@asynccontextmanager
async def _db():
    """A session on the test database, closed on exit (not by the GC)."""
    from app.db.database import get_db
    from app.main import app

    gen = app.dependency_overrides[get_db]()
    try:
        yield await anext(gen)
    finally:
        await gen.aclose()


# 1. The shared cv2.dnn Net must not be driven by two threads at once.
def test_onnx_forward_is_serialised_across_threads() -> None:
    from app.services.detector_cv import DetectorMeta, OnnxYoloxDetector

    class RacyNet:
        """Keeps the last input, like cv2.dnn.Net: interleaving is visible."""

        def __init__(self) -> None:
            self.blob = None
            self.inside = 0
            self.overlap = False

        def setInput(self, blob) -> None:  # noqa: N802 (cv2 API name)
            self.inside += 1
            self.overlap |= self.inside > 1
            self.blob = blob

        def forward(self):
            time.sleep(0.01)  # widen the race window
            out = np.full((1, 3, 6), float(self.blob.mean()), dtype=np.float32)
            self.inside -= 1
            return out

    det = OnnxYoloxDetector.__new__(OnnxYoloxDetector)
    det.meta = DetectorMeta(input_size=(32, 32))
    det.net = RacyNet()
    det._lock = threading.Lock()

    results: dict[int, float] = {}

    def run(value: int) -> None:
        img = np.full((32, 32, 3), value, dtype=np.uint8)
        raw, _, _ = det.raw_forward(img)
        results[value] = float(raw[0, 0])

    threads = [threading.Thread(target=run, args=(v,)) for v in (10, 200, 60, 140)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not det.net.overlap
    assert results == {v: float(v) for v in (10, 200, 60, 140)}


# 2. 'approve' needs an agent count; it must never record a stale or 0 count.
async def test_approve_without_agent_count_is_refused(client, agent_on) -> None:
    from app.models.truth import ScanSession

    body = await _tray_c(client)
    sid = body["scan"]["id"]
    async with _db() as db:
        await db.execute(
            update(ScanSession)
            .where(ScanSession.id == uuid.UUID(sid))
            .values(agent_count=None)
        )
        await db.commit()

    r = await client.post(
        f"/api/v1/scans/{sid}/approve",
        json={"approver_id": "MGR-1", "decision": "approve"},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "NO_AGENT_COUNT"
    ok = await client.post(
        f"/api/v1/scans/{sid}/approve",
        json={"approver_id": "MGR-1", "decision": "correct", "corrected_count": 39},
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["scan"]["final_count"] == 39


# 3. A rejected scan is not "yesterday's approved photo".
async def test_rejected_scan_is_not_a_comparison_reference(client, agent_on) -> None:
    from app.agent.service import previous_approved_scan
    from app.models.truth import ScanSession

    body = await _tray_c(client)
    rejected_id = uuid.UUID(body["scan"]["id"])
    r = await client.post(
        f"/api/v1/scans/{rejected_id}/approve",
        json={"approver_id": "MGR-3", "decision": "reject"},
    )
    assert r.json()["data"]["scan"]["status"] == "needs_recapture"

    async with _db() as db:
        # make the rejected scan unambiguously the most recent one
        await db.execute(
            update(ScanSession)
            .where(ScanSession.id == rejected_id)
            .values(created_at=datetime.utcnow() + timedelta(minutes=5))
        )
        await db.commit()
        probe = ScanSession(id=uuid.uuid4(), tenant_key="default", tray_code="T-C")
        ref = await previous_approved_scan(db, probe)
    assert ref is not None and ref.id != rejected_id
    assert ref.status == "reviewed"


# 4. The agent never re-runs over a human's review.
async def test_agent_run_refused_after_human_review(client, agent_on) -> None:
    body = await _scan(
        client, make_tray(n_items=12, seed=11), expected=12, run_agent="false"
    )
    sid = body["scan"]["id"]
    r = await client.patch(f"/api/v1/scans/{sid}/review", json={"manual_count": 11})
    assert r.status_code == 200
    assert r.json()["data"]["scan"]["status"] == "discrepancy_open"

    rerun = await client.post(f"/api/v1/scans/{sid}/agent-run")
    assert rerun.status_code == 409
    assert rerun.json()["error"]["code"] == "AGENT_RUN_NOT_ALLOWED"
    trace = (await client.get(f"/api/v1/scans/{sid}/trace")).json()["data"]
    assert trace["scan"]["final_count"] == 11  # the human count survives


async def test_agent_run_refused_after_review_without_manual_count(
    client, agent_on, monkeypatch
) -> None:
    from app.core.config import get_settings

    # legacy single shot: the review confirms the machine count, no manual count
    monkeypatch.setattr(get_settings(), "agent_enabled", False)
    body = await _scan(client, make_tray(n_items=12, seed=11), expected=15)
    sid = body["scan"]["id"]
    monkeypatch.setattr(get_settings(), "agent_enabled", True)
    r = await client.patch(
        f"/api/v1/scans/{sid}/review", json={"is_ai_correct": True, "notes": "ok"}
    )
    assert r.status_code == 200
    assert r.json()["data"]["scan"]["status"] == "discrepancy_open"  # runnable
    rerun = await client.post(f"/api/v1/scans/{sid}/agent-run")
    assert rerun.status_code == 409


# 5. The deferred flow (what the PWA uses) keeps the unit value.
async def test_deferred_run_prices_the_variance(client, agent_on) -> None:
    body = await _scan(
        client,
        make_tray(n_items=12, seed=11),
        expected=13,
        run_agent="false",
        unit_value="5000000",
    )
    assert body["scan"]["unit_value"] == 5_000_000
    r = await client.post(f"/api/v1/scans/{body['scan']['id']}/agent-run")
    data = r.json()["data"]
    assert data["scan"]["status"] == "awaiting_approval"
    assert data["discrepancy"]["variance_count"] == -1
    assert data["discrepancy"]["variance_value"] == -5_000_000
    assert data["discrepancy"]["severity"] == "medium"


# 9. A correction re-prices the variance from the corrected count.
async def test_correction_reprices_the_variance(client, agent_on) -> None:
    body = await _tray_c(client)  # unit 2.5M, agent 39 vs POS 40
    assert body["discrepancy"]["variance_value"] == -2_500_000
    r = await client.post(
        f"/api/v1/scans/{body['scan']['id']}/approve",
        json={"approver_id": "MGR-2", "decision": "correct", "corrected_count": 37},
    )
    data = r.json()["data"]
    assert data["scan"]["variance_count"] == -3
    assert data["scan"]["variance_value"] == -7_500_000
    assert data["discrepancy"]["variance_value"] == -7_500_000
    assert data["discrepancy"]["severity"] == "medium"


# 6. Blur / out-of-frame re-shots are capped, then the agent counts and escalates.
def test_blur_and_framing_reshots_are_capped() -> None:
    cfg = PolicyConfig()
    for attempt in range(cfg.max_hard_recaptures):
        obs = Observation(attempt=attempt, assessed=True, tray_coverage=0.05)
        assert decide(obs, cfg).action == Action.REQUEST_RECAPTURE
        obs = Observation(
            attempt=attempt, assessed=True, tray_coverage=0.8, blur_var=10.0
        )
        assert decide(obs, cfg).code == "blur"

    last = cfg.max_hard_recaptures
    obs = Observation(attempt=last, assessed=True, tray_coverage=0.05)
    assert decide(obs, cfg).action == Action.COUNT
    # counted, confident, matches POS, but the tray was barely in frame
    obs.counted, obs.count, obs.expected_count, obs.mean_conf = True, 12, 12, 0.9
    obs.tiled, obs.median_box_frac = True, 0.01
    assert decide(obs, cfg).action == Action.ESCALATE


# 8. A re-run that produces no count clears the old count and discrepancy.
async def test_no_count_rerun_clears_stale_count_and_discrepancy(
    client, agent_on, monkeypatch
) -> None:
    from app.core.config import get_settings
    from app.models.truth import AuditEvent, Discrepancy, ScanSession

    settings = get_settings()
    monkeypatch.setattr(settings, "agent_enabled", False)  # legacy single shot
    body = await _scan(client, make_tray(n_items=12, seed=11), expected=15)
    sid = body["scan"]["id"]
    assert body["scan"]["status"] == "discrepancy_open"
    assert body["discrepancy"]["status"] == "open"

    monkeypatch.setattr(settings, "agent_enabled", True)
    async with _db() as db:
        scan = (
            await db.execute(
                select(ScanSession).where(ScanSession.id == uuid.UUID(sid))
            )
        ).scalar_one()
    # the stored photo now shows heavy glare: the agent asks for a re-shot
    agent_on[scan.image_path] = make_tray(n_items=12, seed=11, glare=0.2).jpeg()

    r = await client.post(f"/api/v1/scans/{sid}/agent-run")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["scan"]["status"] == "needs_recapture"
    assert data["scan"]["agent_count"] is None
    assert data["scan"]["final_count"] == 0
    assert data["scan"]["variance_count"] is None
    assert data["scan"]["boxes_json"] == []
    assert data["discrepancy"] is None
    async with _db() as db:
        rows = (
            (
                await db.execute(
                    select(Discrepancy).where(Discrepancy.scan_id == uuid.UUID(sid))
                )
            )
            .scalars()
            .all()
        )
    assert [d.status for d in rows] == ["ignored"]
    assert rows[0].resolved_by == "trayagent"
    # the count the re-run replaced is kept in the audit trail
    async with _db() as db:
        event = (
            await db.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_id == sid,
                    AuditEvent.action == "SCAN_AGENT_RUN",
                )
            )
        ).scalar_one()
    assert event.payload_json["count"] is None
    assert event.payload_json["before"]["final_count"] == body["scan"]["final_count"]
    assert (
        event.payload_json["before"]["variance_count"] == body["scan"]["variance_count"]
    )
    assert len(event.payload_json["before"]["boxes"]) == body["scan"]["detected_count"]


# 10. The stored object's key and ContentType follow the bytes, not the name.
def test_stored_image_type_follows_the_bytes() -> None:
    from app.services.storage import _image_ext

    jpeg = make_tray().jpeg()
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    assert _image_ext(jpeg, "photo.png") == ".jpg"  # face blur re-encoded it
    assert _image_ext(png, "photo.jpg") == ".png"
    assert _image_ext(b"????", "photo.png") == ".png"
    assert _image_ext(b"????", "photo.bmp") == ".jpg"


# Round 2 of the review.


# A review never records the placeholder 0 of a scan nothing counted.
async def test_review_without_count_of_uncounted_scan_is_refused(
    client, agent_on
) -> None:
    body = await _scan(
        client, make_tray(n_items=12, seed=11), expected=10, run_agent="false"
    )
    sid = body["scan"]["id"]
    r = await client.patch(f"/api/v1/scans/{sid}/review", json={"notes": "ok"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "MANUAL_COUNT_REQUIRED"
    ok = await client.patch(f"/api/v1/scans/{sid}/review", json={"manual_count": 12})
    assert ok.status_code == 200
    assert ok.json()["data"]["scan"]["final_count"] == 12


async def test_review_without_count_keeps_the_machine_count(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "agent_enabled", False)
    from app.services.storage import StorageService

    monkeypatch.setattr(
        StorageService,
        "save_image_and_thumbnail",
        lambda self, payload, name: ("uploads/x.jpg", "thumbnails/x.jpg"),
    )
    body = await _scan(client, make_tray(n_items=12, seed=11), expected=10)
    counted = body["scan"]["detected_count"]
    r = await client.patch(
        f"/api/v1/scans/{body['scan']['id']}/review", json={"is_ai_correct": True}
    )
    assert r.status_code == 200
    assert r.json()["data"]["scan"]["final_count"] == counted


# A rejected photo stays closed: no review can turn it into a reference.
async def test_rejected_scan_cannot_be_reviewed(client, agent_on) -> None:
    body = await _tray_c(client)
    sid = body["scan"]["id"]
    await client.post(
        f"/api/v1/scans/{sid}/approve",
        json={"approver_id": "MGR-3", "decision": "reject"},
    )
    r = await client.patch(f"/api/v1/scans/{sid}/review", json={"manual_count": 40})
    assert r.status_code == 409 and r.json()["error"]["code"] == "SCAN_CLOSED"


# The review marker is a column, not an audit-log lookup.
async def test_review_sets_the_marker_that_locks_the_agent_out(
    client, agent_on
) -> None:
    from app.models.truth import ScanSession

    body = await _scan(
        client, make_tray(n_items=12, seed=11), expected=13, run_agent="false"
    )
    sid = body["scan"]["id"]
    await client.patch(f"/api/v1/scans/{sid}/review", json={"manual_count": 12})
    async with _db() as db:
        scan = (
            await db.execute(
                select(ScanSession).where(ScanSession.id == uuid.UUID(sid))
            )
        ).scalar_one()
        assert scan.reviewed_at is not None
        # even with the count cleared, the review still locks the scan
        scan.manual_count = None
        await db.commit()
    r = await client.post(f"/api/v1/scans/{sid}/agent-run")
    assert r.status_code == 409
    assert "human already decided" in r.json()["error"]["message"]


# A unit value sent before there is a POS figure is kept for later counts.
async def test_unit_value_without_expected_count_is_kept(client, agent_on) -> None:
    body = await _scan(client, make_tray(n_items=12, seed=11), run_agent="false")
    sid = body["scan"]["id"]
    r = await client.patch(
        f"/api/v1/scans/{sid}/review", json={"manual_count": 12, "unit_value": 3000}
    )
    assert r.json()["data"]["scan"]["unit_value"] == 3000
    r = await client.patch(
        f"/api/v1/scans/{sid}/review", json={"manual_count": 12, "expected_count": 10}
    )
    assert r.json()["data"]["scan"]["variance_value"] == 6000


# Round 3 of the review.


async def _set(sid: str, **values) -> None:
    from app.models.truth import ScanSession

    async with _db() as db:
        await db.execute(
            update(ScanSession).where(ScanSession.id == uuid.UUID(sid)).values(**values)
        )
        await db.commit()


# A review cannot land while the agent is counting the same scan.
async def test_review_refused_while_the_agent_runs(client, agent_on) -> None:
    body = await _scan(
        client, make_tray(n_items=12, seed=11), expected=13, run_agent="false"
    )
    sid = body["scan"]["id"]
    await _set(sid, status="agent_running")
    r = await client.patch(f"/api/v1/scans/{sid}/review", json={"manual_count": 12})
    assert r.status_code == 409 and r.json()["error"]["code"] == "AGENT_RUNNING"


# The claim is a compare-and-set: a review that committed after the check wins.
async def test_agent_claim_loses_to_a_review_committed_first(
    client, agent_on, monkeypatch
) -> None:
    import app.api.routes.agent as agent_routes

    body = await _scan(
        client, make_tray(n_items=12, seed=11), expected=13, run_agent="false"
    )
    sid = body["scan"]["id"]
    await client.patch(f"/api/v1/scans/{sid}/review", json={"manual_count": 12})
    await _set(sid, status="pending_review")  # runnable status, but reviewed
    # the in-memory check misses the review (as if it committed right after)
    monkeypatch.setattr(agent_routes, "_human_reviewed", lambda scan: False)
    r = await client.post(f"/api/v1/scans/{sid}/agent-run")
    assert r.status_code == 409
    assert "changed before the agent could start" in r.json()["error"]["message"]
    trace = (await client.get(f"/api/v1/scans/{sid}/trace")).json()["data"]
    assert trace["scan"]["final_count"] == 12


# A run that fails releases the claim, so the scan can still be reviewed.
async def test_failed_agent_run_releases_the_claim(
    client, agent_on, monkeypatch
) -> None:
    import app.api.routes.agent as agent_routes

    async def boom(*args, **kwargs):
        raise RuntimeError("detector crashed")

    body = await _scan(
        client, make_tray(n_items=12, seed=11), expected=13, run_agent="false"
    )
    sid = body["scan"]["id"]
    monkeypatch.setattr(agent_routes, "run_for_scan", boom)
    try:
        await client.post(f"/api/v1/scans/{sid}/agent-run")
    except RuntimeError:
        pass  # ASGITransport re-raises the app's exception
    trace = (await client.get(f"/api/v1/scans/{sid}/trace")).json()["data"]
    assert trace["scan"]["status"] == "pending_review"
    r = await client.patch(f"/api/v1/scans/{sid}/review", json={"manual_count": 12})
    assert r.status_code == 200


# A later review that only adds figures keeps the human's corrected count.
async def test_review_keeps_an_earlier_human_count(client, agent_on) -> None:
    body = await _tray_c(client)  # agent 39 vs POS 40
    sid = body["scan"]["id"]
    await client.post(
        f"/api/v1/scans/{sid}/approve",
        json={"approver_id": "MGR-2", "decision": "correct", "corrected_count": 37},
    )
    r = await client.patch(
        f"/api/v1/scans/{sid}/review", json={"expected_count": 38, "notes": "POS"}
    )
    scan = r.json()["data"]["scan"]
    assert scan["final_count"] == 37 and scan["variance_count"] == -1


# No stored unit value: price from the tray master, like a new scan.
async def test_missing_unit_value_falls_back_to_the_tray_master(
    client, agent_on
) -> None:
    from app.models.truth import Tray

    body = await _scan(
        client, make_tray(n_items=12, seed=11), expected=13, run_agent="false"
    )
    sid = body["scan"]["id"]
    async with _db() as db:
        db.add(Tray(tenant_key="default", tray_code="T-A", unit_value=4000))
        await db.commit()
    await _set(sid, unit_value=None)  # e.g. a scan from before migration 0005
    r = await client.patch(f"/api/v1/scans/{sid}/review", json={"manual_count": 12})
    data = r.json()["data"]
    assert data["scan"]["unit_value"] == 4000
    assert data["discrepancy"]["variance_value"] == -4000


# An approver's unit value is kept even when there is no POS figure yet.
async def test_approval_keeps_unit_value_without_expected_count(
    client, agent_on
) -> None:
    body = await _scan(client, make_tray(n_items=12, seed=11), run_agent="false")
    sid = body["scan"]["id"]
    await _set(sid, status="awaiting_approval", agent_count=12)
    r = await client.post(
        f"/api/v1/scans/{sid}/approve",
        json={
            "approver_id": "MGR-1",
            "decision": "correct",
            "corrected_count": 11,
            "unit_value": 5000,
        },
    )
    assert r.status_code == 200
    assert r.json()["data"]["scan"]["unit_value"] == 5000


# A rejection closes the discrepancy with who and when.
async def test_rejection_records_who_and_when(client, agent_on) -> None:
    body = await _tray_c(client)
    r = await client.post(
        f"/api/v1/scans/{body['scan']['id']}/approve",
        json={"approver_id": "MGR-3", "decision": "reject"},
    )
    d = r.json()["data"]["discrepancy"]
    assert d["status"] == "ignored"
    assert d["resolved_by"] == "MGR-3" and d["resolved_at"] is not None
