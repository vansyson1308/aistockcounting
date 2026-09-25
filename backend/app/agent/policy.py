"""TrayAgent policy (SPEC §4.4): the deterministic decision function and its guardrails.

``decide(obs)`` looks only at the numbers the OpenCV tools produced so far
(the observation) and returns the next action. ``allowed_actions(obs)`` is the
guardrail set: the Bedrock planner may choose only from it, and
``AUTO_ACCEPT`` is in it only when the acceptance conditions hold. The
approval gate therefore does not depend on any model's judgement.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Action(str, Enum):
    ASSESS = "assess_quality"
    REDUCE_GLARE = "reduce_glare"
    COUNT = "count"  # rectify_tray + detect
    TILE = "tile_detect"
    ZOOM = "zoom_recount"
    COMPARE = "compare_previous"
    AUTO_ACCEPT = "auto_accept"
    REQUEST_RECAPTURE = "request_recapture"
    ESCALATE = "escalate"

    @property
    def terminal(self) -> bool:
        return self in TERMINAL


TERMINAL = {Action.AUTO_ACCEPT, Action.REQUEST_RECAPTURE, Action.ESCALATE}


@dataclass(frozen=True)
class PolicyConfig:
    """Thresholds. Provisional until calibrated on the real validation split."""

    max_steps: int = 5
    time_budget_s: float = 20.0
    coverage_min: float = 0.15
    blur_min: float = 60.0
    glare_severe: float = 0.08
    glare_mild: float = 0.01
    max_recaptures: int = 1
    dense_count: int = 60
    small_box_frac: float = 0.0006
    crowding_max: float = 0.35
    uncertain_lo: float = 0.25
    uncertain_hi: float = 0.5
    accept_conf: float = 0.6
    max_zoom_regions: int = 4
    zoom_factor: float = 2.0
    changed_ratio_min: float = 0.00005

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Observation:
    """What the controller knows so far. Numbers only, never images."""

    attempt: int = 0
    expected_count: int | None = None
    has_previous: bool = False
    steps_used: int = 0
    elapsed_s: float = 0.0
    # assess_quality
    assessed: bool = False
    blur_var: float | None = None
    glare_ratio: float | None = None
    tray_coverage: float | None = None
    low_light: bool = False
    # actions done
    glare_reduced: bool = False
    counted: bool = False
    tiled: bool = False
    zoomed: bool = False
    compared: bool = False
    # counting state
    count: int | None = None
    single_shot_count: int | None = None
    mean_conf: float = 0.0
    uncertain_regions: int = 0
    median_box_frac: float = 0.0
    crowding: float = 0.0
    # compare_previous
    compare_aligned: bool | None = None
    changed_regions: int = 0
    changed_ratio: float = 0.0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("notes")
        return d

    @property
    def mismatch(self) -> bool:
        return (
            self.expected_count is not None
            and self.count is not None
            and (self.count != self.expected_count)
        )

    def dense(self, cfg: PolicyConfig) -> bool:
        if not self.count:
            return False
        return (
            self.count >= cfg.dense_count
            or self.median_box_frac < cfg.small_box_frac
            or self.crowding > cfg.crowding_max
        )

    def degraded(self, cfg: PolicyConfig) -> bool:
        """Evidence too weak to auto-accept even if the numbers agree."""
        return bool(
            (self.glare_ratio or 0.0) > cfg.glare_severe
            or self.low_light
            or (self.blur_var is not None and self.blur_var < cfg.blur_min)
        )


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str
    code: str  # machine-readable reason (e.g. "glare", "pos_mismatch")
    params: dict[str, Any] = field(default_factory=dict)


def can_auto_accept(obs: Observation, cfg: PolicyConfig) -> bool:
    return (
        obs.counted
        and not obs.mismatch
        and obs.uncertain_regions == 0
        and obs.mean_conf >= cfg.accept_conf
        and not obs.degraded(cfg)
        and (obs.count or 0) > 0
    )


def recapture_reason(obs: Observation, cfg: PolicyConfig) -> str | None:
    if not obs.assessed:
        return None
    if (obs.tray_coverage or 0.0) < cfg.coverage_min:
        return "tray_not_in_frame"
    if obs.blur_var is not None and obs.blur_var < cfg.blur_min:
        return "blur"
    if obs.attempt < cfg.max_recaptures:
        if (obs.glare_ratio or 0.0) > cfg.glare_severe:
            return "glare"
        if obs.low_light:
            return "low_light"
    return None


def allowed_actions(obs: Observation, cfg: PolicyConfig) -> list[Action]:
    """Guardrails. Every action proposed by any planner must be in this set."""
    if not obs.assessed:
        return [Action.ASSESS]
    allowed: list[Action] = [Action.ESCALATE]
    if not obs.counted and recapture_reason(obs, cfg) is not None:
        allowed.append(Action.REQUEST_RECAPTURE)
    if not obs.counted and not obs.glare_reduced and (obs.glare_ratio or 0.0) > 0:
        allowed.append(Action.REDUCE_GLARE)
    if not obs.counted:
        allowed.append(Action.COUNT)
    else:
        if not obs.tiled:
            allowed.append(Action.TILE)
        if obs.uncertain_regions > 0 and not obs.zoomed:
            allowed.append(Action.ZOOM)
        if obs.has_previous and not obs.compared:
            allowed.append(Action.COMPARE)
        if can_auto_accept(obs, cfg):
            allowed.append(Action.AUTO_ACCEPT)
    return allowed


RECAPTURE_TEXT = {
    "glare": (
        "Glare covers {glare:.0%} of the tray. Tilt the phone about 15 degrees or step "
        "sideways so the ceiling light is not reflected in the tray, then retake."
    ),
    "blur": (
        "The photo is blurry. Rest your elbows on the counter, tap the screen to focus on "
        "the tray, hold still for one second, then retake."
    ),
    "tray_not_in_frame": (
        "The tray fills only {coverage:.0%} of the photo. Move closer so the whole tray "
        "fills the screen with all four corners visible, then retake."
    ),
    "low_light": "The photo is too dark. Turn on the counter light or move the tray to brighter light.",
}


def recapture_instruction(code: str, obs: Observation) -> str:
    return RECAPTURE_TEXT[code].format(
        glare=obs.glare_ratio or 0.0, coverage=obs.tray_coverage or 0.0
    )


def decide(obs: Observation, cfg: PolicyConfig) -> Decision:
    """The deterministic policy of SPEC §4.4."""
    if not obs.assessed:
        return Decision(Action.ASSESS, "Start by checking image quality.", "start")

    if not obs.counted:
        code = recapture_reason(obs, cfg)
        if code is not None:
            return Decision(
                Action.REQUEST_RECAPTURE,
                recapture_instruction(code, obs),
                code,
                {"instruction": recapture_instruction(code, obs)},
            )
        if (obs.glare_ratio or 0.0) > cfg.glare_mild and not obs.glare_reduced:
            return Decision(
                Action.REDUCE_GLARE,
                f"Glare ratio {obs.glare_ratio:.3f} > {cfg.glare_mild}: inpaint highlights "
                "before counting.",
                "glare_mild",
            )
        return Decision(
            Action.COUNT, "Quality is acceptable: rectify the tray and detect.", "count"
        )

    if obs.count == 0 and not obs.tiled:
        return Decision(
            Action.TILE,
            "No items at full-frame resolution: re-detect on tiles in case the items are "
            "too small for one pass.",
            "empty_single_shot",
        )
    if obs.dense(cfg) and not obs.tiled:
        return Decision(
            Action.TILE,
            f"Dense tray (count={obs.count}, median box={obs.median_box_frac:.5f}, "
            f"crowding={obs.crowding:.2f}): re-detect on overlapping tiles.",
            "dense",
        )
    if obs.uncertain_regions > 0 and not obs.zoomed:
        return Decision(
            Action.ZOOM,
            f"{obs.uncertain_regions} uncertain region(s): zoom in and recount them.",
            "uncertain",
        )
    if obs.mismatch and obs.has_previous and not obs.compared:
        return Decision(
            Action.COMPARE,
            f"Count {obs.count} differs from POS {obs.expected_count}: compare with the last "
            "approved photo to localise the change.",
            "pos_mismatch",
        )

    if can_auto_accept(obs, cfg):
        if obs.expected_count is None:
            why = f"Confident count {obs.count} (no POS figure to reconcile)."
        else:
            why = f"Confident count {obs.count} matches POS {obs.expected_count}."
        return Decision(Action.AUTO_ACCEPT, why, "confident_match")
    return escalation(obs, cfg)


def escalation(
    obs: Observation, cfg: PolicyConfig, code: str | None = None
) -> Decision:
    parts: list[str] = []
    if obs.mismatch:
        parts.append(f"count {obs.count} vs POS {obs.expected_count}")
        if obs.compared and obs.compare_aligned:
            if obs.changed_regions:
                parts.append(
                    f"{obs.changed_regions} region(s) changed since the last approved photo"
                )
            else:
                parts.append(
                    "no visible change since the last approved photo (check POS)"
                )
        code = code or "pos_mismatch"
    if obs.uncertain_regions:
        parts.append(f"{obs.uncertain_regions} region(s) still uncertain")
        code = code or "uncertain_regions"
    if obs.counted and obs.mean_conf < cfg.accept_conf:
        parts.append(f"mean confidence {obs.mean_conf:.2f} < {cfg.accept_conf}")
        code = code or "low_confidence"
    if obs.degraded(cfg):
        parts.append("image quality degraded")
        code = code or "degraded_image"
    if obs.counted and not obs.count:
        parts.append("no items detected")
        code = code or "empty"
    code = code or "needs_human"
    text = "; ".join(parts) or "a human decision is required"
    return Decision(Action.ESCALATE, f"Escalate to a human: {text}.", code)
