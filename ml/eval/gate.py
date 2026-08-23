"""Gate 0A verdict logic (plan §X.4), driven by a thresholds YAML.

The primary gate is FINAL association quality (AssA, HOTA, IDF1, long-horizon
identity integrity, team clustering, dense-occlusion audit). The
offline-vs-online delta is an ablation input: reported, never gated on.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml


class Verdict(StrEnum):
    PASS = "PASS"
    CONDITIONAL_PASS = "CONDITIONAL_PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class GateInputs:
    # Final (online + offline) results on the primary fixed-view eval set.
    hota: float  # 0..100
    deta: float  # 0..100
    assa: float  # 0..100
    idf1: float  # 0..100
    identity_integrity_half: float  # 0..1, full-half long-horizon test
    team_cluster_accuracy: float  # 0..1
    # Dense-occlusion audit: does a *systemic* class of evidence-unresolvable
    # identity errors exist? (human evaluation labor, TRAINING/QA ONLY)
    dense_audit_systemic_failure: bool
    # Ablation (reported, not gated):
    offline_delta_hota: float | None = None
    # Context check on broadcast-class clips (optional):
    soccernet_hota: float | None = None
    # For the CONDITIONAL branch: association health on well-detected subsets.
    assa_well_detected: float | None = None


def load_thresholds(path: str | Path) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def decide(inputs: GateInputs, thresholds: dict) -> tuple[Verdict, list[str]]:
    t = thresholds["gate0a"]
    reasons: list[str] = []

    bars = {
        "assa": (inputs.assa, t["assa_min"]),
        "hota": (inputs.hota, t["hota_min"]),
        "idf1": (inputs.idf1, t["idf1_min"]),
    }
    shortfalls = {k: bar - v for k, (v, bar) in bars.items() if v < bar}
    integrity_ok = inputs.identity_integrity_half >= t["identity_integrity_min"]
    team_ok = inputs.team_cluster_accuracy >= t["team_cluster_min"]
    audit_ok = not inputs.dense_audit_systemic_failure
    context_ok = (
        inputs.soccernet_hota is None
        or inputs.soccernet_hota >= t["soccernet_hota_min"]
    )

    if inputs.offline_delta_hota is not None:
        reasons.append(
            f"ablation: offline pass delta = {inputs.offline_delta_hota:+.1f} HOTA "
            "(reported, not gated)"
        )

    # ---- PASS: every absolute bar met.
    if not shortfalls and integrity_ok and team_ok and audit_ok and context_ok:
        reasons.append("all §X.4 absolute bars met on final association quality")
        return Verdict.PASS, reasons

    # ---- FAIL: association-limited profile that offline evidence cannot fix.
    assa_fail = inputs.assa < t["assa_fail_below"]
    deta_healthy = inputs.deta >= t["deta_healthy_min"]
    integrity_fail = inputs.identity_integrity_half < t["identity_integrity_fail_below"]
    if assa_fail and deta_healthy and integrity_fail and not audit_ok:
        reasons.append(
            "AssA-limited failure with healthy DetA, low long-horizon integrity, "
            "and systemic evidence-unresolvable errors in the dense audit "
            "(§X.4 FAIL profile — re-architect, do not iterate)"
        )
        return Verdict.FAIL, reasons

    # ---- CONDITIONAL: near-miss that is detection-limited, association healthy.
    margin = t["conditional_margin"]
    near_miss = all(s <= margin for s in shortfalls.values()) if shortfalls else True
    assa_wd = inputs.assa_well_detected
    det_limited = (
        inputs.deta < t["deta_healthy_min"]
        and assa_wd is not None
        and assa_wd >= t["assa_min"]
    )
    if near_miss and det_limited and audit_ok:
        reasons.append(
            f"near-miss (max shortfall ≤ {margin} pts), DetA-limited "
            "(association healthy on well-detected subsets) — detection deficits "
            "are buyable via tiling/resolution/camera geometry"
        )
        return Verdict.CONDITIONAL_PASS, reasons

    # ---- Anything else needs human analysis before a call is made.
    for k, s in shortfalls.items():
        reasons.append(f"{k} short of bar by {s:.1f} pts")
    if not integrity_ok:
        reasons.append(
            f"long-horizon identity integrity "
            f"{inputs.identity_integrity_half:.3f} < {t['identity_integrity_min']}"
        )
    if not team_ok:
        reasons.append(
            f"team clustering {inputs.team_cluster_accuracy:.3f} < "
            f"{t['team_cluster_min']}"
        )
    if not audit_ok:
        reasons.append("dense-occlusion audit found systemic failures")
    if not context_ok:
        reasons.append("broadcast-clip context check below bar")
    reasons.append("profile matches neither PASS, CONDITIONAL, nor FAIL — analyze")
    return Verdict.INCONCLUSIVE, reasons
