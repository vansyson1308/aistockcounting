"""Gate 0A evaluator sanity checks (instructions §3).

A — perfect prediction: GT fed back as prediction ⇒ HOTA/DetA/AssA/IDF1 ≈ 1,
    IDSW = 0.
B — deliberately broken IDs: GT boxes kept, persistent IDs permuted at a
    period boundary ⇒ detection metrics stay high, association metrics
    materially degrade.
C — missing detections: a controlled fraction of GT boxes deleted ⇒
    DetA / completeness degrade in the expected direction, association of
    what remains stays intact.

Runs on ANY MOTChallenge gt.txt. Exits non-zero if any expectation fails —
experiment progression must stop and the evaluator be debugged (§3).
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from ml.eval.metrics import evaluate_tracking
from ml.eval.mot_io import read_mot
from ml.eval.trackeval_wrapper import hota_from_frames


def _copy(frames):
    return {f: list(v) for f, v in frames.items()}


def permute_ids(frames, seed: int = 0, n_segments: int = 4):
    """Swap identity labels between objects, changing the permutation every
    segment boundary — boxes untouched, identities broken."""
    rng = random.Random(seed)
    all_frames = sorted(frames)
    seg_len = max(1, len(all_frames) // n_segments)
    ids = sorted({tid for v in frames.values() for tid, _, _ in v})
    out = {}
    perm = list(ids)
    for i, f in enumerate(all_frames):
        if i % seg_len == 0:
            perm = list(ids)
            rng.shuffle(perm)
        mapping = dict(zip(ids, perm, strict=True))
        out[f] = [(mapping[tid], box, conf) for tid, box, conf in frames[f]]
    return out


def drop_boxes(frames, fraction: float, seed: int = 0):
    rng = random.Random(seed)
    out = {}
    for f, dets in frames.items():
        kept = [d for d in dets if rng.random() >= fraction]
        if kept:
            out[f] = kept
    return out


def run(gt_path: Path, out_path: Path | None, drop_fraction: float = 0.3) -> dict:
    gt = read_mot(gt_path)

    def score(pred):
        native = evaluate_tracking(gt, pred).as_dict()
        native.update({k: round(v, 4) for k, v in hota_from_frames(gt, pred).items()})
        return native

    a = score(_copy(gt))
    b = score(permute_ids(gt))
    c = score(drop_boxes(gt, drop_fraction))

    checks = {
        "A_perfect_hota_1": a["hota"] > 0.999,
        "A_perfect_deta_1": a["deta"] > 0.999,
        "A_perfect_assa_1": a["assa"] > 0.999,
        "A_perfect_idf1_1": a["idf1"] > 0.999,
        "A_perfect_idsw_0": a["id_switches"] == 0,
        "B_detection_stays_high": b["deta"] > 0.999,
        "B_association_degrades": b["assa"] < 0.6 and b["idf1"] < 0.7,
        "B_switches_appear": b["id_switches"] > 0,
        "C_deta_degrades": c["deta"] < 0.999 and c["deta"] > 0.2,
        "C_completeness_tracks_drop": abs(c["completeness"] - (1 - drop_fraction))
        < 0.05,
        "C_surviving_identity_intact": c["identity_integrity"] > 0.999,
    }
    result = {
        "gt": str(gt_path),
        "n_gt_boxes": a["num_gt_boxes"],
        "A_perfect_prediction": a,
        "B_permuted_ids": b,
        "C_dropped_boxes": {"drop_fraction": drop_fraction, **c},
        "checks": checks,
        "all_passed": all(checks.values()),
    }
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gt", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--drop-fraction", type=float, default=0.3)
    args = ap.parse_args()
    result = run(args.gt, args.out, args.drop_fraction)
    for name, ok in result["checks"].items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print("sanity:", "ALL PASSED" if result["all_passed"] else "FAILURES — STOP")
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
