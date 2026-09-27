"""Every branch of the deterministic policy (SPEC §4.4) and its guardrails."""

import pytest

from app.agent.policy import (
    Action,
    Observation,
    PolicyConfig,
    allowed_actions,
    can_auto_accept,
    decide,
)

CFG = PolicyConfig()


def assessed(**kw) -> Observation:
    base = dict(assessed=True, blur_var=500.0, glare_ratio=0.0, tray_coverage=0.6)
    base.update(kw)
    return Observation(**base)


def counted(**kw) -> Observation:
    base = dict(
        counted=True,
        count=12,
        single_shot_count=12,
        mean_conf=0.85,
        median_box_frac=0.004,
        crowding=0.0,
        expected_count=12,
    )
    base.update(kw)
    return assessed(**base)


def test_first_action_is_assess_and_only_assess_allowed() -> None:
    obs = Observation()
    assert decide(obs, CFG).action == Action.ASSESS
    assert allowed_actions(obs, CFG) == [Action.ASSESS]


@pytest.mark.parametrize(
    ("kw", "code"),
    [
        ({"tray_coverage": 0.05}, "tray_not_in_frame"),
        ({"blur_var": 10.0}, "blur"),
        ({"glare_ratio": 0.2}, "glare"),
        ({"low_light": True}, "low_light"),
    ],
)
def test_capture_problems_request_recapture(kw, code) -> None:
    d = decide(assessed(**kw), CFG)
    assert d.action == Action.REQUEST_RECAPTURE
    assert d.code == code
    assert d.params["instruction"]
    assert Action.REQUEST_RECAPTURE in allowed_actions(assessed(**kw), CFG)


def test_recapture_text_is_specific() -> None:
    d = decide(assessed(glare_ratio=0.2), CFG)
    assert "20%" in d.reason and "Tilt" in d.reason


def test_severe_glare_after_reshot_is_reduced_not_rejected_again() -> None:
    obs = assessed(glare_ratio=0.2, attempt=1)
    assert decide(obs, CFG).action == Action.REDUCE_GLARE


def test_mild_glare_reduces_then_counts() -> None:
    obs = assessed(glare_ratio=0.03)
    assert decide(obs, CFG).action == Action.REDUCE_GLARE
    obs.glare_reduced = True
    assert decide(obs, CFG).action == Action.COUNT


def test_good_quality_counts() -> None:
    assert decide(assessed(), CFG).action == Action.COUNT


@pytest.mark.parametrize(
    "kw",
    [
        {"count": 80, "expected_count": 80},
        {"median_box_frac": 0.0001},
        {"crowding": 0.6},
    ],
)
def test_dense_triggers_tile(kw) -> None:
    assert decide(counted(**kw), CFG).action == Action.TILE


def test_empty_single_shot_tries_tiles() -> None:
    d = decide(counted(count=0, mean_conf=0.0), CFG)
    assert d.action == Action.TILE and d.code == "empty_single_shot"


def test_uncertain_triggers_zoom_after_tile() -> None:
    obs = counted(uncertain_regions=2)
    assert decide(obs, CFG).action == Action.ZOOM
    dense = counted(uncertain_regions=2, count=90, expected_count=90)
    assert decide(dense, CFG).action == Action.TILE
    dense.tiled = True
    assert decide(dense, CFG).action == Action.ZOOM


def test_mismatch_with_previous_compares() -> None:
    obs = counted(count=11, has_previous=True)
    d = decide(obs, CFG)
    assert d.action == Action.COMPARE and d.code == "pos_mismatch"


def test_mismatch_without_previous_escalates() -> None:
    d = decide(counted(count=11), CFG)
    assert d.action == Action.ESCALATE and d.code == "pos_mismatch"


def test_after_compare_escalation_mentions_changes() -> None:
    obs = counted(
        count=11,
        has_previous=True,
        compared=True,
        compare_aligned=True,
        changed_regions=1,
    )
    d = decide(obs, CFG)
    assert d.action == Action.ESCALATE
    assert "1 region(s) changed" in d.reason
    obs.changed_regions = 0
    assert "no visible change" in decide(obs, CFG).reason


def test_confident_match_auto_accepts() -> None:
    d = decide(counted(), CFG)
    assert d.action == Action.AUTO_ACCEPT and "matches POS 12" in d.reason


def test_no_pos_confident_auto_accepts() -> None:
    d = decide(counted(expected_count=None), CFG)
    assert d.action == Action.AUTO_ACCEPT and "no POS" in d.reason


@pytest.mark.parametrize(
    ("kw", "code"),
    [
        ({"mean_conf": 0.4}, "low_confidence"),
        ({"uncertain_regions": 1, "zoomed": True}, "uncertain_regions"),
        ({"glare_ratio": 0.2, "attempt": 1, "glare_reduced": True}, "degraded_image"),
        (
            {"count": 0, "expected_count": None, "mean_conf": 0.0, "tiled": True},
            "low_confidence",
        ),
    ],
)
def test_weak_evidence_escalates(kw, code) -> None:
    d = decide(counted(**kw), CFG)
    assert d.action == Action.ESCALATE
    assert d.code == code


@pytest.mark.parametrize(
    "kw",
    [
        {"count": 11},  # POS mismatch
        {"uncertain_regions": 1},
        {"mean_conf": 0.3},
        {"glare_ratio": 0.2},
        {"count": 0, "expected_count": 0},
        {"view_conflicts": 1, "tiled": True, "zoomed": True},
    ],
)
def test_guardrail_never_allows_auto_accept_on_weak_evidence(kw) -> None:
    obs = counted(**kw)
    assert not can_auto_accept(obs, CFG)
    assert Action.AUTO_ACCEPT not in allowed_actions(obs, CFG)
    assert Action.ESCALATE in allowed_actions(obs, CFG)


def test_recapture_not_allowed_once_counted() -> None:
    obs = counted(glare_ratio=0.2)
    assert Action.REQUEST_RECAPTURE not in allowed_actions(obs, CFG)


def test_actions_are_not_repeated() -> None:
    obs = counted(
        tiled=True, zoomed=True, compared=True, has_previous=True, uncertain_regions=1
    )
    allowed = allowed_actions(obs, CFG)
    for a in (Action.TILE, Action.ZOOM, Action.COMPARE, Action.COUNT, Action.ASSESS):
        assert a not in allowed


def test_view_conflict_escalates_even_when_count_matches_pos() -> None:
    obs = counted(view_conflicts=2, tiled=True, zoomed=True, single_shot_count=13)
    d = decide(obs, CFG)
    assert d.action == Action.ESCALATE and d.code == "view_conflict"
    assert "disagree in 2 cell(s)" in d.reason
