from app.agent import cloudwatch, progress
from app.agent.controller import run_agent
from app.agent.trace import decision_events, step_rows
from app.services.detector_cv import ClassicalDetector
from tests.fixtures.synth_tray import make_tray


def test_progress_registry_lifecycle() -> None:
    progress.start("s1", "r1")
    progress.add_step("s1", {"seq": 1})
    live = progress.get("s1")
    assert live["running"] is True and live["steps"] == [{"seq": 1}]
    progress.finish("s1")
    assert progress.get("s1")["running"] is False
    progress.add_step("unknown", {"seq": 1})  # ignored
    assert progress.get("unknown") is None


def test_cloudwatch_metric_payload() -> None:
    data = cloudwatch.metric_data(
        {
            "decision": "escalate",
            "steps_used": 5,
            "elapsed_ms": 1234,
            "planner_fallbacks": 1,
        }
    )
    by_name = {d["MetricName"]: d for d in data}
    assert by_name["Escalated"]["Value"] == 1.0
    assert by_name["AgentSteps"]["Value"] == 5.0
    assert by_name["AgentLatencyMs"]["Unit"] == "Milliseconds"
    assert by_name["RecaptureRequested"]["Value"] == 0.0


def test_cloudwatch_publish_never_raises(monkeypatch) -> None:
    class Boom:
        def put_metric_data(self, **kw):
            raise RuntimeError("no creds")

    monkeypatch.setattr(cloudwatch, "_client", Boom())
    cloudwatch.publish(
        {"decision": "auto_accept", "steps_used": 2, "elapsed_ms": 10}, "NS", "r"
    )


def test_trace_rows_and_decision_events() -> None:
    import uuid

    r = run_agent(
        make_tray(seed=11).image, detector=ClassicalDetector(), expected_count=12
    )
    sid = uuid.uuid4()
    rows = step_rows(r, scan_id=sid, tenant="t")
    assert [x.tool for x in rows] == [e.tool for e in r.trace]
    assert all(x.run_id == r.run_id and x.scan_id == sid for x in rows)
    events = decision_events(r, scan_id=sid, tenant="t", actor_id="EMP")
    decisions = [
        e.payload_json.get("decision") for e in events if e.action == "AGENT_DECISION"
    ]
    assert decisions == ["assess_quality", "count", "auto_accept"]
    assert events[-1].action == "AGENT_RUN_COMPLETED"
    count_event = next(e for e in events if e.payload_json.get("decision") == "count")
    assert count_event.payload_json["tools"] == ["rectify_tray", "detect"]
