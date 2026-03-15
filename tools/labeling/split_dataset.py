#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
from collections import Counter
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
    p.add_argument("--labels-in", dest="labels_inp", default=None,
                   help="Labels source dir. Default: derived from --in by replacing images→labels")
    p.add_argument("--mode", choices=["copy", "symlink"], default="copy")
    args = p.parse_args()

    if round(args.train + args.val + args.test, 4) != 1.0:
        raise SystemExit("train+val+test must equal 1.0")

    inp = Path(args.inp)
    root = inp.parent.parent  # e.g. datasets/vj_items

    # Derive labels source: replace "images" with "labels" in the path
    if args.labels_inp:
        labels_inp = Path(args.labels_inp)
    else:
        labels_inp = root / "labels" / "all"

    has_labels = labels_inp.is_dir()
    if not has_labels:
        print(f"WARNING: Labels directory not found: {labels_inp}")
        print("         Only images will be split. Labels must be placed manually.")

    # Create output directories
    for split in ["train", "val", "test"]:
        (root / "images" / split).mkdir(parents=True, exist_ok=True)
        if has_labels:
            (root / "labels" / split).mkdir(parents=True, exist_ok=True)

    # Split images and labels
    counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()

    images = sorted([x for x in inp.iterdir() if x.is_file() and not x.name.startswith(".")])

    for image in images:
        split = bucket_for(image.name, args.train, args.val)
        counts[split] += 1

        # Copy/symlink image
        target = root / "images" / split / image.name
        if target.exists() or target.is_symlink():
            target.unlink()
        if args.mode == "copy":
            shutil.copy2(image, target)
        else:
            target.symlink_to(image.resolve())

        # Copy/symlink matching label file
        if has_labels:
            label_src = labels_inp / f"{image.stem}.txt"
            if label_src.exists():
                label_dst = root / "labels" / split / f"{image.stem}.txt"
                if label_dst.exists() or label_dst.is_symlink():
                    label_dst.unlink()
                if args.mode == "copy":
                    shutil.copy2(label_src, label_dst)
                else:
                    label_dst.symlink_to(label_src.resolve())
                label_counts[split] += 1

    # Summary
    print("Dataset split complete.")
    print(f"  Total images: {len(images)}")
    for split in ["train", "val", "test"]:
        label_info = f", {label_counts[split]} labels" if has_labels else ""
        print(f"  {split}: {counts[split]} images{label_info}")

    if has_labels:
        missing = len(images) - sum(label_counts.values())
        if missing > 0:
            print(f"  WARNING: {missing} images have no matching label file")


if __name__ == "__main__":
    main()
