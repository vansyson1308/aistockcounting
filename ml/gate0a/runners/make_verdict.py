"""Assemble the official Gate 0A verdict (instructions §22).

Reads final TEST metrics from a metrics JSON, feeds them through the FROZEN
decision function (ml.eval.gate.decide + ml/gate0a/thresholds.yaml — never
modified after seeing results), and writes reports/gate0a/verdict.json.

If required real-data evidence is missing (e.g. the primary dataset was
never executable in the environment), the status is BLOCKED — a verdict is
NEVER fabricated from partial evidence.

Input metrics JSON shape (produced by the runbook's final scoring step):
{
  "final_test": {"hota":..,"deta":..,"assa":..,"idf1":..},          # 0..100
  "long_horizon": {"identity_integrity": 0..1},
  "team": {"player_minute_accuracy": 0..1},
  "dense_audit": {"systemic_failure": bool},
  "ablation": {"offline_delta_hota": float|null},
  "context": {"soccernet_hota": float|null},
  "conditional_inputs": {"assa_well_detected": float|null}
}
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from ml.eval.gate import GateInputs, decide, load_thresholds

REQUIRED = [
    ("final_test", "hota"),
    ("final_test", "deta"),
    ("final_test", "assa"),
    ("final_test", "idf1"),
    ("long_horizon", "identity_integrity"),
    ("team", "player_minute_accuracy"),
    ("dense_audit", "systemic_failure"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--metrics", type=Path, default=None,
                    help="final TEST metrics JSON; omit only with --blocked")
    ap.add_argument("--blocked", default=None,
                    help="declare BLOCKED with this reason (no verdict issued)")
    ap.add_argument("--evidence", type=Path, nargs="*", default=[],
                    help="evidence artifact paths recorded in the verdict")
    ap.add_argument("--out", type=Path,
                    default=Path("reports/gate0a/verdict.json"))
    args = ap.parse_args()

    thresholds_path = Path("ml/gate0a/thresholds.yaml")
    record: dict = {
        "gate": "0A",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "thresholds_sha256": hashlib.sha256(
            thresholds_path.read_bytes()
        ).hexdigest(),
        "evidence": [str(p) for p in args.evidence],
    }

    if args.blocked:
        record["status"] = "BLOCKED"
        record["verdict"] = None
        record["reason"] = args.blocked
    else:
        m = json.loads(args.metrics.read_text())
        missing = [
            f"{a}.{b}" for a, b in REQUIRED
            if m.get(a, {}).get(b) is None
        ]
        if missing:
            record["status"] = "BLOCKED"
            record["verdict"] = None
            record["reason"] = f"required final metrics missing: {missing}"
        else:
            inputs = GateInputs(
                hota=m["final_test"]["hota"],
                deta=m["final_test"]["deta"],
                assa=m["final_test"]["assa"],
                idf1=m["final_test"]["idf1"],
                identity_integrity_half=m["long_horizon"]["identity_integrity"],
                team_cluster_accuracy=m["team"]["player_minute_accuracy"],
                dense_audit_systemic_failure=m["dense_audit"]["systemic_failure"],
                offline_delta_hota=m.get("ablation", {}).get("offline_delta_hota"),
                soccernet_hota=m.get("context", {}).get("soccernet_hota"),
                assa_well_detected=m.get("conditional_inputs", {}).get(
                    "assa_well_detected"
                ),
            )
            verdict, reasons = decide(inputs, load_thresholds(thresholds_path))
            record["status"] = "DECIDED"
            record["verdict"] = str(verdict)
            record["reasons"] = reasons
            record["inputs"] = vars(inputs)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
