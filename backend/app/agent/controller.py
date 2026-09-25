"""TrayAgent controller: a bounded perception -> decision -> action state machine.

Each loop iteration:
1. **Decide.** The planner (deterministic, or Bedrock with a deterministic
   fallback) picks the next action from ``allowed_actions(obs)``. The choice
   depends only on the numbers the OpenCV tools produced so far.
2. **Enforce the budget.** At most ``max_steps`` perception steps and
   ``time_budget_s`` seconds. A non-terminal action beyond the budget turns
   into ``escalate(budget_exhausted)``.
3. **Act.** Run the OpenCV tool(s) for that action, store each tool's evidence
   image, and append one trace entry per tool call.

Terminal actions (``auto_accept``, ``request_recapture``, ``escalate``) render
the evidence sheet and end the run. Nothing here writes to the database.
Persistence is ``trace.py``'s job, so the loop stays unit-testable.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import cv2
import numpy as np

from app.agent.policy import (
    Action,
    Decision,
    Observation,
    PolicyConfig,
    allowed_actions,
    decide,
    escalation,
    recapture_instruction,
    recapture_reason,
)
from app.agent.tools import (
    assess_quality,
    compare_previous,
    detect,
    rectify_tray,
    reduce_glare,
    regions_from_dets,
    render_evidence,
    tile_detect,
    zoom_recount,
)
from app.agent.tools.types import Rect, center_in, clip_rect
from app.cv.imageio import encode_jpeg, resize_max_side
from app.services.detector_cv import Det, Detector

logger = logging.getLogger("app")

WORK_MAX_SIDE = 2048
EVIDENCE_MAX_SIDE = 1600


class EvidenceStore(Protocol):
    def put(self, key: str, data: bytes) -> str: ...


class MemoryEvidenceStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> str:
        self.objects[key] = data
        return key


class Planner(Protocol):
    name: str

    def propose(
        self, obs: Observation, allowed: list[Action], cfg: PolicyConfig
    ) -> tuple[Action, str]: ...


class DeterministicPlanner:
    name = "deterministic"

    def propose(
        self, obs: Observation, allowed: list[Action], cfg: PolicyConfig
    ) -> tuple[Action, str]:
        d = decide(obs, cfg)
        return d.action, d.reason


@dataclass
class TraceEntry:
    seq: int
    step_no: int  # 0 for terminal actions and planner events
    tool: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    evidence_key: str | None
    decision: str  # the action this entry belongs to
    reason: str
    latency_ms: int
    planner: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "step_no": self.step_no,
            "tool": self.tool,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "evidence_key": self.evidence_key,
            "decision": self.decision,
            "reason": self.reason,
            "latency_ms": self.latency_ms,
            "planner": self.planner,
        }


@dataclass
class AgentResult:
    run_id: uuid.UUID
    action: Action
    code: str
    reason: str
    instruction: str | None
    count: int | None
    single_shot_count: int | None
    steps_used: int
    elapsed_ms: int
    planner: str
    planner_fallbacks: int
    evidence_key: str | None
    dets: list[Det]
    uncertain_regions: list[Rect]
    changed_regions: list[Rect]
    observation: Observation
    trace: list[TraceEntry] = field(default_factory=list)
    dets_original: list[Det] = field(
        default_factory=list
    )  # in the uploaded image's pixels

    def summary(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "decision": self.action.value,
            "code": self.code,
            "reason": self.reason,
            "instruction": self.instruction,
            "count": self.count,
            "single_shot_count": self.single_shot_count,
            "steps_used": self.steps_used,
            "elapsed_ms": self.elapsed_ms,
            "planner": self.planner,
            "planner_fallbacks": self.planner_fallbacks,
            "evidence_key": self.evidence_key,
            "uncertain_regions": [list(r) for r in self.uncertain_regions],
            "changed_regions": [list(r) for r in self.changed_regions],
        }


def _map_rect(r: Rect, H: np.ndarray, shape: tuple[int, int]) -> Rect:
    x, y, w, h = r
    pts = np.array([[[x, y], [x + w, y], [x + w, y + h], [x, y + h]]], np.float32)
    p = cv2.perspectiveTransform(pts, H)[0]
    x0, y0 = p.min(axis=0)
    x1, y1 = p.max(axis=0)
    return clip_rect((int(x0), int(y0), int(x1 - x0), int(y1 - y0)), shape[1], shape[0])


class _Run:
    """Mutable state of one agent run (kept private to this module)."""

    def __init__(
        self,
        image: np.ndarray,
        detector: Detector,
        cfg: PolicyConfig,
        evidence: EvidenceStore,
        key_prefix: str,
        clock: Callable[[], float],
        on_step: Callable[[TraceEntry], None] | None,
    ) -> None:
        self.original, self.scale = resize_max_side(image, WORK_MAX_SIDE)
        self.work = self.original  # after glare reduction
        self.rect = self.original  # rectified working frame
        self.H = np.eye(3)  # original -> rectified
        self.detector = detector
        self.cfg = cfg
        self.evidence = evidence
        self.key_prefix = key_prefix
        self.clock = clock
        self.on_step = on_step
        self.t0 = clock()
        self.trace: list[TraceEntry] = []
        self.dets: list[Det] = []
        self.uncertain: list[Rect] = []
        self.changed: list[Rect] = []
        self.heatmap: np.ndarray | None = None
        self.tray_quad: np.ndarray | None = None

    def elapsed(self) -> float:
        return self.clock() - self.t0

    def record(
        self,
        tool: str,
        step_no: int,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        evidence_img: np.ndarray | None,
        decision: str,
        reason: str,
        latency_ms: int,
        planner: str,
    ) -> TraceEntry:
        seq = len(self.trace) + 1
        key = None
        if evidence_img is not None:
            small, _ = resize_max_side(evidence_img, EVIDENCE_MAX_SIDE)
            key = self.evidence.put(
                f"{self.key_prefix}/{seq:02d}_{tool}.jpg", encode_jpeg(small, 82)
            )
        entry = TraceEntry(
            seq,
            step_no,
            tool,
            inputs,
            outputs,
            key,
            decision,
            reason,
            latency_ms,
            planner,
        )
        self.trace.append(entry)
        if self.on_step is not None:
            try:
                self.on_step(entry)
            except Exception:  # progress reporting must never break a run
                logger.exception("on_step callback failed")
        return entry


def to_original(dets: list[Det], H: np.ndarray, scale: float) -> list[Det]:
    """Map detections from the rectified working frame back to upload pixels."""
    if not dets:
        return []
    Hinv = np.linalg.inv(H)
    out: list[Det] = []
    for d in dets:
        pts = np.array(
            [[[d.x, d.y], [d.x + d.w, d.y], [d.x + d.w, d.y + d.h], [d.x, d.y + d.h]]],
            np.float32,
        )
        p = cv2.perspectiveTransform(pts, Hinv)[0] / scale
        x0, y0 = p.min(axis=0)
        x1, y1 = p.max(axis=0)
        out.append(Det(float(x0), float(y0), float(x1 - x0), float(y1 - y0), d.conf))
    return out


def _ms(t0: float, clock: Callable[[], float]) -> int:
    return int((clock() - t0) * 1000)


def run_agent(
    image: np.ndarray,
    *,
    detector: Detector,
    expected_count: int | None = None,
    previous_image: np.ndarray | None = None,
    previous_ref: str | None = None,
    attempt: int = 0,
    cfg: PolicyConfig | None = None,
    planner: Planner | None = None,
    evidence: EvidenceStore | None = None,
    key_prefix: str | None = None,
    run_id: uuid.UUID | None = None,
    clock: Callable[[], float] = time.perf_counter,
    on_step: Callable[[TraceEntry], None] | None = None,
) -> AgentResult:
    cfg = cfg or PolicyConfig()
    planner = planner or DeterministicPlanner()
    evidence = evidence or MemoryEvidenceStore()
    run_id = run_id or uuid.uuid4()
    key_prefix = key_prefix or f"evidence/adhoc/{run_id.hex}"
    st = _Run(image, detector, cfg, evidence, key_prefix, clock, on_step)
    obs = Observation(
        attempt=attempt,
        expected_count=expected_count,
        has_previous=previous_image is not None,
    )
    active_planner: Planner = planner
    fallbacks = 0

    while True:
        obs.elapsed_s = round(st.elapsed(), 3)
        allowed = allowed_actions(obs, cfg)
        decision = decide(obs, cfg)
        planner_name = active_planner.name
        if active_planner.name != "deterministic":
            t_plan = clock()
            try:
                proposed, why = active_planner.propose(obs, allowed, cfg)
                if proposed not in allowed:
                    raise ValueError(
                        f"planner proposed {proposed!r}, not in {[a.value for a in allowed]}"
                    )
                decision = _decision_from_planner(proposed, why, obs, cfg, decision)
            except Exception as exc:
                fallbacks += 1
                st.record(
                    "planner",
                    0,
                    {"allowed": [a.value for a in allowed]},
                    {"error": str(exc)[:300]},
                    None,
                    "planner_fallback",
                    f"{active_planner.name} planner failed; deterministic controller takes over.",
                    _ms(t_plan, clock),
                    active_planner.name,
                )
                active_planner = DeterministicPlanner()
                planner_name = "deterministic"

        if not decision.action.terminal and (
            obs.steps_used >= cfg.max_steps or st.elapsed() >= cfg.time_budget_s
        ):
            what = (
                f"{obs.steps_used} steps"
                if obs.steps_used >= cfg.max_steps
                else f"{st.elapsed():.1f}s"
            )
            base = escalation(obs, cfg)
            decision = Decision(
                Action.ESCALATE,
                f"Budget exhausted ({what}) before '{decision.action.value}'. {base.reason}",
                "budget_exhausted",
            )

        if decision.action.terminal:
            return _finish(st, obs, decision, planner_name, fallbacks, run_id)

        obs.steps_used += 1
        _act(st, obs, decision, planner_name, previous_image, previous_ref)


def _decision_from_planner(
    action: Action, why: str, obs: Observation, cfg: PolicyConfig, default: Decision
) -> Decision:
    if action == default.action:
        return Decision(
            action, f"{default.reason} [planner: {why}]", default.code, default.params
        )
    if action == Action.REQUEST_RECAPTURE:
        code = recapture_reason(obs, cfg) or "planner"
        text = (
            recapture_instruction(code, obs)
            if code in {"glare", "blur", "tray_not_in_frame", "low_light"}
            else why
        )
        return Decision(action, text, code, {"instruction": text})
    if action == Action.ESCALATE:
        base = escalation(obs, cfg)
        return Decision(action, f"{base.reason} [planner: {why}]", base.code)
    return Decision(action, f"[planner] {why}", "planner")


def _refresh_counts(st: _Run, obs: Observation) -> None:
    obs.count = len(st.dets)
    obs.mean_conf = float(np.mean([d.conf for d in st.dets])) if st.dets else 0.0
    obs.uncertain_regions = len(st.uncertain)


def _act(
    st: _Run,
    obs: Observation,
    decision: Decision,
    planner: str,
    previous_image: np.ndarray | None,
    previous_ref: str | None,
) -> None:
    cfg, clock, step = st.cfg, st.clock, obs.steps_used
    a = decision.action
    if a == Action.ASSESS:
        t = clock()
        q = assess_quality(st.work)
        st.tray_quad = q.tray_quad
        obs.assessed = True
        obs.blur_var = q.metrics["blur_var"]
        obs.glare_ratio = q.metrics["glare_ratio"]
        obs.tray_coverage = q.metrics["tray_coverage"]
        obs.low_light = "low_light" in q.flags
        st.record(
            "assess_quality",
            step,
            {
                "size": [int(st.work.shape[1]), int(st.work.shape[0])],
                "attempt": obs.attempt,
            },
            q.outputs(),
            q.evidence,
            a.value,
            decision.reason,
            _ms(t, clock),
            planner,
        )
    elif a == Action.REDUCE_GLARE:
        t = clock()
        g = reduce_glare(st.work)
        st.work = g.image
        st.rect = g.image
        obs.glare_reduced = True
        st.record(
            "reduce_glare",
            step,
            {"radius": 5},
            g.outputs(),
            g.evidence,
            a.value,
            decision.reason,
            _ms(t, clock),
            planner,
        )
    elif a == Action.COUNT:
        t = clock()
        r = rectify_tray(st.work, quad=st.tray_quad)
        st.rect, st.H = r.image, r.homography
        st.record(
            "rectify_tray",
            step,
            {"quad_from": "assess_quality" if st.tray_quad is not None else "search"},
            r.outputs(),
            r.evidence,
            a.value,
            decision.reason,
            _ms(t, clock),
            planner,
        )
        t = clock()
        d = detect(st.rect, st.detector)
        st.dets = list(d.dets)
        st.uncertain = regions_from_dets(d.dets, d.uncertain_idx, st.rect.shape[:2])
        obs.counted = True
        obs.single_shot_count = d.count
        obs.median_box_frac, obs.crowding = d.median_box_frac, d.crowding
        _refresh_counts(st, obs)
        st.record(
            "detect",
            step,
            {
                "frame": "rectified" if r.found else "original",
                "detector": st.detector.name,
            },
            d.outputs(),
            d.evidence,
            a.value,
            decision.reason,
            _ms(t, clock),
            planner,
        )
    elif a == Action.TILE:
        t = clock()
        single = list(st.dets)
        tr = tile_detect(
            st.rect,
            st.detector,
            single_shot=single,
            median_box_frac=obs.median_box_frac,
        )
        st.dets = list(tr.dets)
        uncertain = regions_from_dets(tr.dets, tr.uncertain_idx, st.rect.shape[:2])
        for cell in tr.disagreement:
            n_tiled = sum(center_in((d.x, d.y, d.w, d.h), cell) for d in tr.dets)
            n_single = sum(center_in((d.x, d.y, d.w, d.h), cell) for d in single)
            if (
                n_tiled < n_single
            ):  # tiling lost items here: a human or zoom should look
                uncertain.append(cell)
        st.uncertain = uncertain
        obs.tiled = True
        _refresh_counts(st, obs)
        st.record(
            "tile_detect",
            step,
            {"grid": list(tr.grid), "overlap": 0.2, "single_shot": len(single)},
            tr.outputs(),
            tr.evidence,
            a.value,
            decision.reason,
            _ms(t, clock),
            planner,
        )
    elif a == Action.ZOOM:
        t = clock()
        regions = st.uncertain[: cfg.max_zoom_regions]
        rest = st.uncertain[cfg.max_zoom_regions :]
        z = zoom_recount(
            st.rect,
            st.detector,
            regions,
            st.dets,
            zoom=cfg.zoom_factor,
            accept_conf=cfg.uncertain_hi,
        )
        st.dets = list(z.dets)
        st.uncertain = list(z.unresolved) + rest
        obs.zoomed = True
        _refresh_counts(st, obs)
        st.record(
            "zoom_recount",
            step,
            {"regions": [list(r) for r in regions], "zoom": cfg.zoom_factor},
            z.outputs(),
            z.evidence,
            a.value,
            decision.reason,
            _ms(t, clock),
            planner,
        )
    elif a == Action.COMPARE:
        assert previous_image is not None
        t = clock()
        prev, _ = resize_max_side(previous_image, WORK_MAX_SIDE)
        # Changed blobs smaller than ~a third of a typical item are noise.
        min_frac = (
            float(np.clip(0.3 * obs.median_box_frac, 5e-5, 2e-3))
            if obs.median_box_frac
            else 3e-4
        )
        c = compare_previous(st.original, prev, min_region_frac=min_frac)
        obs.compared = True
        obs.compare_aligned = c.aligned
        obs.changed_ratio = c.changed_ratio
        significant = c.aligned and c.changed_ratio >= cfg.changed_ratio_min
        st.changed = (
            [_map_rect(r, st.H, st.rect.shape[:2]) for r in c.regions]
            if significant
            else []
        )
        st.heatmap = c.evidence if c.aligned else None
        obs.changed_regions = len(st.changed)
        st.record(
            "compare_previous",
            step,
            {"previous": previous_ref},
            c.outputs(),
            c.evidence,
            a.value,
            decision.reason,
            _ms(t, clock),
            planner,
        )
    else:  # pragma: no cover - terminal actions never reach here
        raise AssertionError(a)


def _finish(
    st: _Run,
    obs: Observation,
    decision: Decision,
    planner: str,
    fallbacks: int,
    run_id: uuid.UUID,
) -> AgentResult:
    t = st.clock()
    a = decision.action
    instruction = decision.params.get("instruction")
    if a == Action.AUTO_ACCEPT:
        headline = f"AUTO-ACCEPT  count={obs.count}" + (
            f"  = POS {obs.expected_count}" if obs.expected_count is not None else ""
        )
    elif a == Action.REQUEST_RECAPTURE:
        headline = f"RE-SHOOT REQUESTED ({decision.code})"
    else:
        headline = f"ESCALATED TO HUMAN ({decision.code})  count={obs.count}" + (
            f"  POS={obs.expected_count}" if obs.expected_count is not None else ""
        )
    image = st.rect if obs.counted else st.work
    sheet = render_evidence(
        image,
        st.dets,
        headline=headline,
        details=[instruction or decision.reason],
        uncertain_regions=st.uncertain,
        changed_regions=st.changed,
        diff_heatmap=st.heatmap if a == Action.ESCALATE else None,
    )
    entry = st.record(
        "render_evidence",
        0,
        {"terminal": a.value},
        sheet.outputs(),
        sheet.evidence,
        a.value,
        decision.reason,
        _ms(t, st.clock),
        planner,
    )
    return AgentResult(
        run_id=run_id,
        action=a,
        code=decision.code,
        reason=decision.reason,
        instruction=instruction,
        count=obs.count,
        single_shot_count=obs.single_shot_count,
        steps_used=obs.steps_used,
        elapsed_ms=int(st.elapsed() * 1000),
        planner=planner,
        planner_fallbacks=fallbacks,
        evidence_key=entry.evidence_key,
        dets=st.dets,
        uncertain_regions=st.uncertain,
        changed_regions=st.changed,
        observation=obs,
        trace=st.trace,
        dets_original=to_original(st.dets, st.H, st.scale),
    )
