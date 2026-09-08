"""Diagnostic contract loading, hashing, and the maturity decision.

The decision is a pure function of (contract, evidence). It never touches the
official gate thresholds and never emits PASS/FAIL vocabulary.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONTRACT_PATH = Path(__file__).with_name("diagnostic_contract.yaml")

LEVEL_1 = "LEVEL 1 — ARCHITECTURE / EXPERIMENTAL CORE"
LEVEL_15 = "LEVEL 1.5 — REAL PIPELINE RUNS, QUALITY INSUFFICIENT"
LEVEL_2 = "LEVEL 2 — WORKING CV PROTOTYPE"


def load_contract(path: Path | str = CONTRACT_PATH) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def contract_sha256(path: Path | str = CONTRACT_PATH) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass
class Evidence:
    """Everything the maturity decision consumes (all rates are fractions)."""

    chain_ran_end_to_end: bool
    clips_scored: list[str]
    open_p4_hota: float | None
    open_p4_deta: float | None
    recall_ge40px_combined: float | None
    bottleneck_label: str | None
    notes: list[str] = field(default_factory=list)


def decide_maturity(contract: dict, ev: Evidence) -> dict:
    c = contract["level2_criteria"]
    checks: dict[str, bool] = {}
    checks["chain_ran_end_to_end"] = bool(ev.chain_ran_end_to_end)
    required = list(c["clips_scored"])
    checks["all_final_clips_scored"] = all(k in ev.clips_scored for k in required)

    def ge(value: float | None, bar: float) -> bool:
        return value is not None and float(value) >= float(bar)

    checks["open_p4_hota_ge_min"] = ge(ev.open_p4_hota, c["open_play_hota_min"])
    checks["open_p4_deta_ge_min"] = ge(ev.open_p4_deta, c["deta_min"])
    checks["recall_ge40px_ge_min"] = ge(
        ev.recall_ge40px_combined, c["recall_ge40px_min"]
    )
    checks["bottleneck_identified"] = bool(
        ev.bottleneck_label and ev.bottleneck_label != "UNDETERMINED"
    )

    if not checks["chain_ran_end_to_end"] or not checks["all_final_clips_scored"]:
        level = LEVEL_1
        summary = "REAL-VIDEO PROBE DID NOT EXECUTE END-TO-END"
    elif all(checks.values()):
        level = LEVEL_2
        summary = "REAL FIXED-CAMERA FOOTBALL VIDEO — NO MANUAL TRACK REPAIR"
    else:
        level = LEVEL_15
        summary = "REAL-VIDEO PROBE DID NOT CLEAR LEVEL-2 BAR"

    missing = [k for k, ok in checks.items() if not ok]
    return {
        "banner": "DIAGNOSTIC — NOT OFFICIAL GATE 0A VERDICT / TEST SET UNTOUCHED",
        "maturity": level,
        "summary": summary,
        "checks": checks,
        "missing": missing,
        "evidence": {
            "clips_scored": ev.clips_scored,
            "open_p4_hota": ev.open_p4_hota,
            "open_p4_deta": ev.open_p4_deta,
            "recall_ge40px_combined": ev.recall_ge40px_combined,
            "bottleneck_label": ev.bottleneck_label,
        },
        "bars": {
            "open_play_hota_min": c["open_play_hota_min"],
            "deta_min": c["deta_min"],
            "recall_ge40px_min": c["recall_ge40px_min"],
        },
        "notes": list(ev.notes),
        "not_a_gate_verdict": True,
    }
