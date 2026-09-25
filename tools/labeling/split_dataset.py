#!/usr/bin/env python3
"""Split the labeled pool 70/15/15 with a fixed seed and FREEZE the test set.

* Stratified by the ``hard`` flag in ``manifest.csv`` (from ingest_raw.py), so
  hard cases (glare, blur, dense) are represented in every split.
* Freezing writes ``splits/test.manifest.sha256`` (sha256 of every test image and
  label) and ``splits/SPLIT_INFO.json``. Once a frozen test set exists,
  re-running NEVER moves an image into or out of test: new images can only go to
  train/val. Use ``--verify`` before any evaluation to prove that the test set is
  unchanged. Thresholds are tuned on val, never on test.

Usage:
    python tools/labeling/split_dataset.py --root datasets/vj_items --seed 42
    python tools/labeling/split_dataset.py --root datasets/vj_items --verify
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
SPLITS = ("train", "val", "test")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_hard(root: Path) -> set[str]:
    manifest = root / "manifest.csv"
    if not manifest.exists():
        return set()
    with manifest.open() as fh:
        return {
            row["file"]
            for row in csv.DictReader(fh)
            if row.get("hard") in {"1", "true"}
        }


def assign(
    names: list[str], hard: set[str], ratios: tuple[float, float, float], seed: int
) -> dict[str, str]:
    """Seeded, stratified 70/15/15 assignment (deterministic for a given input)."""
    rng = random.Random(seed)
    out: dict[str, str] = {}
    for stratum in (
        sorted(n for n in names if n in hard),
        sorted(n for n in names if n not in hard),
    ):
        items = list(stratum)
        rng.shuffle(items)
        n = len(items)
        n_train = round(n * ratios[0])
        n_val = round(n * ratios[1])
        for i, name in enumerate(items):
            out[name] = (
                "train" if i < n_train else ("val" if i < n_train + n_val else "test")
            )
    return out


def load_frozen(root: Path) -> dict[str, str] | None:
    path = root / "splits" / "test.manifest.sha256"
    if not path.exists():
        return None
    frozen: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if line.strip():
            digest, rel = line.split("  ", 1)
            frozen[rel] = digest
    return frozen


def verify(root: Path) -> list[str]:
    """Return a list of problems ([] means the frozen test set is intact)."""
    frozen = load_frozen(root)
    if frozen is None:
        return ["no frozen test manifest (splits/test.manifest.sha256)"]
    problems = []
    for rel, digest in frozen.items():
        p = root / rel
        if not p.exists():
            problems.append(f"missing: {rel}")
        elif sha256(p) != digest:
            problems.append(f"changed: {rel}")
    test_imgs = {
        f"images/test/{p.name}"
        for p in (root / "images" / "test").glob("*")
        if p.suffix.lower() in IMAGE_EXTS
    }
    extra = test_imgs - set(frozen)
    problems.extend(f"unexpected test image: {x}" for x in sorted(extra))
    return problems


def split(
    root: Path, seed: int, ratios: tuple[float, float, float], freeze: bool = True
) -> dict[str, int]:
    pool_imgs = root / "images" / "all"
    pool_lbls = root / "labels" / "all"
    names = sorted(
        p.name for p in pool_imgs.iterdir() if p.suffix.lower() in IMAGE_EXTS
    )
    unlabeled = [n for n in names if not (pool_lbls / f"{Path(n).stem}.txt").exists()]
    if unlabeled:
        raise SystemExit(
            f"{len(unlabeled)} image(s) have no reviewed label (e.g. {unlabeled[0]}). "
            "Export from CVAT first."
        )
    frozen = load_frozen(root)
    frozen_test = (
        {Path(rel).name for rel in frozen if rel.startswith("images/test/")}
        if frozen
        else set()
    )
    if frozen:
        # The frozen test set is fixed; the rest splits train/val in the same proportion.
        rest = [n for n in names if n not in frozen_test]
        tv = ratios[0] + ratios[1]
        mapping = assign(
            rest, read_hard(root), (ratios[0] / tv, ratios[1] / tv, 0.0), seed
        )
        mapping.update({n: "test" for n in frozen_test})
    else:
        mapping = assign(names, read_hard(root), ratios, seed)

    for s in SPLITS:
        for kind in ("images", "labels"):
            d = root / kind / s
            if s == "test" and frozen:
                continue  # never touch a frozen test directory
            if d.exists():
                shutil.rmtree(d)
            d.mkdir(parents=True, exist_ok=True)
    counts = {s: 0 for s in SPLITS}
    (root / "splits").mkdir(exist_ok=True)
    lists: dict[str, list[str]] = {s: [] for s in SPLITS}
    for name, s in sorted(mapping.items()):
        counts[s] += 1
        lists[s].append(name)
        if s == "test" and frozen:
            continue
        shutil.copy2(pool_imgs / name, root / "images" / s / name)
        stem = Path(name).stem
        shutil.copy2(pool_lbls / f"{stem}.txt", root / "labels" / s / f"{stem}.txt")
    for s in SPLITS:
        (root / "splits" / f"{s}.txt").write_text(
            "".join(f"images/{s}/{n}\n" for n in lists[s])
        )

    if freeze and not frozen:
        lines = []
        for name in lists["test"]:
            for rel in (f"images/test/{name}", f"labels/test/{Path(name).stem}.txt"):
                lines.append(f"{sha256(root / rel)}  {rel}")
        (root / "splits" / "test.manifest.sha256").write_text("\n".join(lines) + "\n")
    hard = read_hard(root)
    info = {
        "seed": seed,
        "ratios": list(ratios),
        "counts": counts,
        "hard_per_split": {s: sum(n in hard for n in lists[s]) for s in SPLITS},
        "frozen": True if (freeze or frozen) else False,
        "created_or_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (root / "splits" / "SPLIT_INFO.json").write_text(json.dumps(info, indent=2) + "\n")
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--root", default="datasets/vj_items")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--ratios", type=float, nargs=3, default=(0.7, 0.15, 0.15))
    ap.add_argument("--no-freeze", action="store_true")
    ap.add_argument(
        "--verify", action="store_true", help="only verify the frozen test set"
    )
    args = ap.parse_args()
    root = Path(args.root)
    if args.verify:
        problems = verify(root)
        if problems:
            raise SystemExit("FROZEN TEST SET CHANGED:\n  " + "\n  ".join(problems))
        print("frozen test set verified")
        return
    if abs(sum(args.ratios) - 1.0) > 1e-6:
        raise SystemExit("ratios must sum to 1")
    print(split(root, args.seed, tuple(args.ratios), freeze=not args.no_freeze))


if __name__ == "__main__":
    main()
