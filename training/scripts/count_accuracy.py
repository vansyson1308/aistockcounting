#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from ultralytics import YOLO


def gt_count(label_file: Path) -> int:
    if not label_file.exists():
        return 0
    return len([ln for ln in label_file.read_text(encoding="utf-8").splitlines() if ln.strip()])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", required=True)
    p.add_argument("--split", default="val", choices=["train", "val", "test"])
    p.add_argument("--root", default="datasets/vj_items")
    p.add_argument("--conf", type=float, default=0.25)
    args = p.parse_args()

    run_dir = Path(args.run_dir)
    model = YOLO(str(run_dir / "weights" / "best.pt"))

    img_dir = Path(args.root) / "images" / args.split
    lbl_dir = Path(args.root) / "labels" / args.split

    n = 0
    exact = 0
    mae_sum = 0.0
    error_dist: Counter[int] = Counter()

    for img in sorted([x for x in img_dir.iterdir() if x.is_file() and not x.name.startswith(".")]):
        gt = gt_count(lbl_dir / f"{img.stem}.txt")
        pred = model.predict(str(img), conf=args.conf, verbose=False)[0]
        pc = int(len(pred.boxes))
        err = pc - gt
        error_dist[err] += 1
        mae_sum += abs(err)
        exact += int(err == 0)
        n += 1

    result = {
        "split": args.split,
        "samples": n,
        "exact_match_rate": (exact / n) if n else None,
        "mean_absolute_error": (mae_sum / n) if n else None,
        "error_distribution": dict(sorted(error_dist.items(), key=lambda x: int(x[0]))),
    }
    (run_dir / f"count_accuracy_{args.split}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
