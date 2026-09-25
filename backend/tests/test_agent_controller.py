"""Controller loop tests: each demo path, budgets, planner fallback, trace/evidence."""

import itertools

import numpy as np
import pytest

from app.agent.controller import (
    DeterministicPlanner,
    MemoryEvidenceStore,
    run_agent,
    to_original,
)
from app.agent.planner import (
    BedrockPlanner,
    build_planner,
    parse_tool_choice,
    tool_config,
)
from app.agent.policy import Action, PolicyConfig
from app.services.detector_cv import ClassicalDetector, Det
from tests.fixtures.synth_tray import make_tray

DET = ClassicalDetector()


def tools(result) -> list[str]:
    return [e.tool for e in result.trace]


def test_tray_a_clean_auto_accepts_with_full_trace() -> None:
    tray = make_tray(n_items=12, seed=11)
    store = MemoryEvidenceStore()
    r = run_agent(
        tray.image,
        detector=DET,
        expected_count=12,
        evidence=store,
        key_prefix="evidence/t/a",
    )
    assert r.action == Action.AUTO_ACCEPT
    assert r.count == 12 and r.steps_used == 2
    assert tools(r) == ["assess_quality", "rectify_tray", "detect", "render_evidence"]
    # every tool call stored an evidence image and has a reason and latency
    assert all(e.evidence_key in store.objects for e in r.trace)
    assert all(e.evidence_key.startswith("evidence/t/a/") for e in r.trace)
    assert all(store.objects[e.evidence_key][:3] == b"\xff\xd8\xff" for e in r.trace)
    assert all(e.reason and e.latency_ms >= 0 for e in r.trace)
    assert [e.seq for e in r.trace] == [1, 2, 3, 4]
    assert r.trace[-1].step_no == 0  # the terminal action is not a step
    assert len(r.dets_original) == 12


def test_tray_b_glare_requests_specific_reshot_then_reshot_accepts() -> None:
    glare = make_tray(n_items=12, seed=12, glare=0.2)
    r = run_agent(glare.image, detector=DET, expected_count=12)
    assert r.action == Action.REQUEST_RECAPTURE and r.code == "glare"
    assert "Tilt the phone" in r.instruction
    assert r.count is None and tools(r) == ["assess_quality", "render_evidence"]
    reshot = make_tray(n_items=12, seed=12)
    r2 = run_agent(reshot.image, detector=DET, expected_count=12, attempt=1)
    assert r2.action == Action.AUTO_ACCEPT and r2.count == 12


def test_blur_requests_reshot() -> None:
    r = run_agent(make_tray(blur=31).image, detector=DET, expected_count=12)
    assert r.action == Action.REQUEST_RECAPTURE and r.code == "blur"


def test_mild_glare_is_reduced_before_counting() -> None:
    tray = make_tray(glare=0.03, seed=4)
    r = run_agent(tray.image, detector=DET, expected_count=12)
    assert tools(r)[:2] == ["assess_quality", "reduce_glare"]
    assert r.count == tray.count and r.action == Action.AUTO_ACCEPT


def test_dense_tray_tiles_and_opencv_output_changes_count() -> None:
    # A close-up (the tray fills the frame), so rectification cannot zoom in for us.
    tray = make_tray(n_items=120, item_radius=(7, 9), seed=2, tray_frac=1.0)
    r = run_agent(
        tray.image, detector=ClassicalDetector(input_side=640), expected_count=120
    )
    assert "tile_detect" in tools(r)
    assert r.single_shot_count < 110  # single shot misses tiny items
    assert abs(r.count - 120) <= 2  # the agentic count recovers them


def test_tray_c_dense_mismatch_compares_and_escalates() -> None:
    prev = make_tray(n_items=120, item_radius=(7, 9), seed=2)
    curr = make_tray(
        n_items=120, item_radius=(7, 9), seed=2, exclude_items=[40], perspective=0.05
    )
    r = run_agent(
        curr.image,
        detector=ClassicalDetector(input_side=640),
        expected_count=120,
        previous_image=prev.image,
        previous_ref="scan-prev",
    )
    assert r.action == Action.ESCALATE and r.code == "pos_mismatch"
    assert tools(r) == [
        "assess_quality",
        "rectify_tray",
        "detect",
        "tile_detect",
        "compare_previous",
        "render_evidence",
    ]
    assert len(r.changed_regions) == 1
    assert "1 region(s) changed" in r.reason
    cmp = next(e for e in r.trace if e.tool == "compare_previous")
    assert cmp.inputs == {"previous": "scan-prev"}


class ZoomSensitive:
    """Scripted detector: item 0 is weak at full frame and confident when zoomed."""

    name, version = "scripted", "t"

    def __init__(self, tray):
        self.boxes = tray.boxes

    def detect(self, img):
        h, w = img.shape[:2]
        if max(h, w) >= 900:  # full frame
            return [Det(20, 20, 40, 40, 0.3)] + [
                Det(100 + 60 * i, 400, 40, 40, 0.9) for i in range(11)
            ]
        return [Det(w / 2 - 20, h / 2 - 20, 40, 40, 0.92)]


def test_uncertain_region_is_zoomed_and_resolved() -> None:
    tray = make_tray(n_items=12, seed=3, tray_frac=1.0)
    r = run_agent(tray.image, detector=ZoomSensitive(tray), expected_count=12)
    assert "zoom_recount" in tools(r)
    z = next(e for e in r.trace if e.tool == "zoom_recount")
    assert z.outputs["regions"][0]["resolved"] is True
    assert r.action == Action.AUTO_ACCEPT


def test_budget_exhaustion_by_steps_escalates() -> None:
    tray = make_tray(n_items=120, item_radius=(7, 9), seed=2)
    r = run_agent(
        tray.image,
        detector=ClassicalDetector(input_side=640),
        expected_count=120,
        cfg=PolicyConfig(max_steps=2),
    )
    assert r.action == Action.ESCALATE and r.code == "budget_exhausted"
    assert r.steps_used == 2
    assert "tile_detect" not in tools(r)
    assert "Budget exhausted" in r.reason


def test_budget_exhaustion_by_time_escalates() -> None:
    ticks = itertools.count(0.0, 30.0)  # every clock read advances 30 s
    r = run_agent(
        make_tray().image, detector=DET, expected_count=12, clock=lambda: next(ticks)
    )
    assert r.action == Action.ESCALATE and r.code == "budget_exhausted"
    assert r.steps_used <= 1


def test_five_step_budget_holds_on_the_hardest_path() -> None:
    prev = make_tray(n_items=120, item_radius=(7, 9), seed=2)
    curr = make_tray(
        n_items=120, item_radius=(7, 9), seed=2, exclude_items=[40], glare=0.012
    )
    r = run_agent(
        curr.image,
        detector=ClassicalDetector(input_side=640),
        expected_count=120,
        previous_image=prev.image,
    )
    assert r.steps_used <= 5
    assert r.action == Action.ESCALATE


class RaisingPlanner:
    name = "bedrock"

    def propose(self, obs, allowed, cfg):
        raise TimeoutError("bedrock timed out")


class IllegalPlanner:
    name = "bedrock"

    def propose(self, obs, allowed, cfg):
        return Action.AUTO_ACCEPT, "looks fine to me"


class EchoPlanner:
    name = "bedrock"

    def __init__(self):
        self.calls = 0

    def propose(self, obs, allowed, cfg):
        self.calls += 1
        return DeterministicPlanner().propose(obs, allowed, cfg)


@pytest.mark.parametrize("planner", [RaisingPlanner(), IllegalPlanner()])
def test_planner_failure_falls_back_to_deterministic(planner) -> None:
    tray = make_tray(n_items=12, seed=11)
    r = run_agent(tray.image, detector=DET, expected_count=11, planner=planner)
    assert r.planner_fallbacks == 1
    fb = [e for e in r.trace if e.tool == "planner"]
    assert len(fb) == 1 and fb[0].decision == "planner_fallback"
    # same outcome as the deterministic controller: POS mismatch -> escalate
    assert r.action == Action.ESCALATE and r.planner == "deterministic"


def test_illegal_planner_cannot_auto_accept_a_mismatch() -> None:
    tray = make_tray(n_items=12, seed=11)
    r = run_agent(tray.image, detector=DET, expected_count=13, planner=IllegalPlanner())
    assert r.action != Action.AUTO_ACCEPT


def test_valid_planner_is_used_and_traced() -> None:
    p = EchoPlanner()
    r = run_agent(make_tray(seed=11).image, detector=DET, expected_count=12, planner=p)
    assert p.calls >= 3 and r.planner == "bedrock" and r.planner_fallbacks == 0
    assert all(e.planner == "bedrock" for e in r.trace)
    assert r.action == Action.AUTO_ACCEPT


def test_on_step_callback_and_its_failures() -> None:
    seen = []
    run_agent(make_tray().image, detector=DET, expected_count=12, on_step=seen.append)
    assert [e.seq for e in seen] == [1, 2, 3, 4]

    def boom(_):
        raise RuntimeError("progress sink down")

    r = run_agent(make_tray().image, detector=DET, expected_count=12, on_step=boom)
    assert r.action == Action.AUTO_ACCEPT


def test_to_original_inverts_homography_and_scale() -> None:
    H = np.array([[2.0, 0, 10], [0, 2.0, 20], [0, 0, 1]])
    out = to_original([Det(30, 40, 20, 20, 0.9)], H, scale=0.5)
    d = out[0]
    assert (d.x, d.y, d.w, d.h) == pytest.approx((20.0, 20.0, 20.0, 20.0))


class FakeBedrock:
    def __init__(self, name="count", fail=False):
        self.name, self.fail, self.requests = name, fail, []

    def converse(self, **kw):
        self.requests.append(kw)
        if self.fail:
            raise RuntimeError("AccessDeniedException")
        return {
            "stopReason": "tool_use",
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"text": "thinking"},
                        {
                            "toolUse": {
                                "toolUseId": "t1",
                                "name": self.name,
                                "input": {"reason": "ok"},
                            }
                        },
                    ],
                }
            },
        }


def test_bedrock_planner_request_and_parse() -> None:
    from app.agent.policy import Observation

    client = FakeBedrock("count")
    p = BedrockPlanner(client, "model-x")
    obs = Observation(assessed=True, blur_var=500, glare_ratio=0.0, tray_coverage=0.6)
    action, why = p.propose(obs, [Action.ESCALATE, Action.COUNT], PolicyConfig())
    assert action == Action.COUNT and why == "ok"
    req = client.requests[0]
    assert req["modelId"] == "model-x"
    assert req["toolConfig"]["toolChoice"] == {"any": {}}
    names = [t["toolSpec"]["name"] for t in req["toolConfig"]["tools"]]
    assert names == ["escalate", "count"]
    assert "image" not in str(req["messages"])  # numbers only


def test_bedrock_planner_end_to_end_with_failure_fallback() -> None:
    p = BedrockPlanner(FakeBedrock(fail=True), "model-x")
    r = run_agent(make_tray(seed=11).image, detector=DET, expected_count=12, planner=p)
    assert r.planner_fallbacks == 1 and r.action == Action.AUTO_ACCEPT


def test_parse_tool_choice_rejects_text_only() -> None:
    with pytest.raises(ValueError):
        parse_tool_choice(
            {
                "stopReason": "end_turn",
                "output": {"message": {"content": [{"text": "hi"}]}},
            }
        )
    with pytest.raises(ValueError):
        parse_tool_choice(
            {
                "output": {
                    "message": {
                        "content": [{"toolUse": {"name": "delete_db", "input": {}}}]
                    }
                }
            }
        )


def test_tool_config_schema() -> None:
    cfg = tool_config([Action.ESCALATE])
    spec = cfg["tools"][0]["toolSpec"]
    assert spec["inputSchema"]["json"]["required"] == ["reason"]


def test_build_planner_defaults(monkeypatch) -> None:
    class S:
        agent_planner = "deterministic"
        bedrock_model_id = ""
        aws_region = "ap-southeast-1"
        bedrock_timeout_s = 3.0

    assert build_planner(S()).name == "deterministic"
    S.agent_planner = "bedrock"
    assert build_planner(S()).name == "deterministic"  # no model id configured
    S.bedrock_model_id = "some-model"
    assert build_planner(S()).name == "bedrock"
