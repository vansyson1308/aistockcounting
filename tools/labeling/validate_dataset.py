#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def validate_label_file(path: Path, min_wh: float) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return ["missing_label"]
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        parts = line.strip().split()
        if len(parts) != 5:
            errors.append(f"line {i}: invalid columns")
            continue
        try:
            cls = int(parts[0])
            vals = [float(x) for x in parts[1:]]
        except ValueError:
            errors.append(f"line {i}: non-numeric values")
            continue
        if cls != 0:
            errors.append(f"line {i}: class id must be 0")
        x, y, w, h = vals
        if not all(0 <= v <= 1 for v in [x, y, w, h]):
            errors.append(f"line {i}: values must be in [0,1]")
        if w <= 0 or h <= 0:
            errors.append(f"line {i}: degenerate bbox")
        if w < min_wh or h < min_wh:
            errors.append(f"line {i}: tiny bbox")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="datasets/vj_items")
    parser.add_argument("--min-wh", type=float, default=0.003)
    args = parser.parse_args()

    root = Path(args.root)
    bad: list[str] = []
    total = 0

    for split in ["train", "val", "test"]:
        img_dir = root / "images" / split
        lbl_dir = root / "labels" / split
        for img in sorted([x for x in img_dir.iterdir() if x.is_file() and not x.name.startswith(".")]):
            total += 1
            lbl = lbl_dir / f"{img.stem}.txt"
            errors = validate_label_file(lbl, args.min_wh)
            if errors:
                bad.append(f"{split}/{img.name}: {', '.join(errors)}")

    print(f"Checked {total} images")
    if bad:
        print("Invalid files:")
        for x in bad:
            print("-", x)
        raise SystemExit(1)
    print("Dataset validation passed")


if __name__ == "__main__":
    main()
