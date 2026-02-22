#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ultralytics import YOLO


def to_float(v):
    try:
        return float(v)
    except Exception:
        return None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", required=True)
    p.add_argument("--data", default="datasets/vj_items/data.yaml")
    args = p.parse_args()

    run_dir = Path(args.run_dir)
    best = run_dir / "weights" / "best.pt"
    if not best.exists():
        raise SystemExit(f"Missing model: {best}")

    model = YOLO(str(best))
    val = model.val(data=args.data, split="val")

    metrics = {
        "map50": to_float(val.box.map50),
        "map5095": to_float(val.box.map),
        "precision": to_float(val.box.mp),
        "recall": to_float(val.box.mr),
    }

    test_metrics = None
    try:
        test = model.val(data=args.data, split="test")
        test_metrics = {
            "map50": to_float(test.box.map50),
            "map5095": to_float(test.box.map),
            "precision": to_float(test.box.mp),
            "recall": to_float(test.box.mr),
        }
    except Exception as exc:
        test_metrics = {"warning": str(exc)}

    out = {"val": metrics, "test": test_metrics}
    (run_dir / "eval_metrics.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
