#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path


def bucket_for(name: str, train: float, val: float) -> str:
    h = int(hashlib.sha1(name.encode("utf-8")).hexdigest(), 16) % 10_000
    ratio = h / 10_000
    if ratio < train:
        return "train"
    if ratio < train + val:
        return "val"
    return "test"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--train", type=float, default=0.8)
    p.add_argument("--val", type=float, default=0.1)
    p.add_argument("--test", type=float, default=0.1)
    p.add_argument("--in", dest="inp", default="datasets/vj_items/images/all")
    p.add_argument("--mode", choices=["copy", "symlink"], default="copy")
    args = p.parse_args()

    if round(args.train + args.val + args.test, 4) != 1.0:
        raise SystemExit("train+val+test must equal 1.0")

    inp = Path(args.inp)
    root = inp.parent.parent
    for split in ["train", "val", "test"]:
        (root / "images" / split).mkdir(parents=True, exist_ok=True)

    for image in sorted([x for x in inp.iterdir() if x.is_file() and not x.name.startswith(".")]):
        split = bucket_for(image.name, args.train, args.val)
        target = root / "images" / split / image.name
        if target.exists() or target.is_symlink():
            target.unlink()
        if args.mode == "copy":
            shutil.copy2(image, target)
        else:
            target.symlink_to(image.resolve())

    print("Dataset split complete.")


if __name__ == "__main__":
    main()
