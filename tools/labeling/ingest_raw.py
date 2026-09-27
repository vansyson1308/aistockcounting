#!/usr/bin/env python3
"""Ingest the owner's raw tray photos into the labeling pool.

    datasets/vj_items/raw/            photos (any names; JPEG/PNG/HEIC→convert first)
    datasets/vj_items/raw/hard/       hard cases (glare, blur, dense) - tagged "hard"
    datasets/vj_items/raw/pairs/      <tray>_prev.jpg / <tray>_curr.jpg (compare_previous eval)
    datasets/vj_items/raw/demo/       demo trays A/B/C (never used for training or test)

For each photo in raw/ and raw/hard/ this script applies the EXIF orientation,
blurs faces (OpenCV YuNet, the same code as the API), caps the long side at
MAX_SIDE, and writes ``images/all/<sha1-12>.jpg`` plus a manifest row
(``datasets/vj_items/manifest.csv``: file, source, sha1, hard, width, height).
Pairs and demo photos are copied (face-blurred) to ``images/pairs`` and
``images/demo``. Re-running is idempotent (content-addressed names).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.privacy import blur_faces  # noqa: E402

EXTS = {".jpg", ".jpeg", ".png"}
MAX_SIDE = 2560


def _load(path: Path):
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)  # applies EXIF orientation
    if img is None:
        raise ValueError(f"cannot decode {path}")
    h, w = img.shape[:2]
    s = min(1.0, MAX_SIDE / max(h, w))
    if s < 1.0:
        img = cv2.resize(
            img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA
        )
    return img


def _write(img, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img, [cv2.IMWRITE_JPEG_QUALITY, 93])


def ingest(root: Path) -> dict[str, int]:
    raw = root / "raw"
    if not raw.is_dir():
        raise SystemExit(f"no raw folder at {raw}")
    rows: list[dict] = []
    stats = {
        "pool": 0,
        "hard": 0,
        "pairs": 0,
        "demo": 0,
        "faces_blurred": 0,
        "skipped": 0,
    }
    for sub, hard in (("", False), ("hard", True)):
        folder = raw / sub if sub else raw
        if not folder.is_dir():
            continue
        for p in sorted(folder.iterdir()):
            if not p.is_file() or p.suffix.lower() not in EXTS:
                continue
            try:
                img = _load(p)
            except ValueError:
                stats["skipped"] += 1
                continue
            res = blur_faces(img)
            stats["faces_blurred"] += res.faces
            digest = hashlib.sha1(p.read_bytes()).hexdigest()
            name = f"{digest[:12]}.jpg"
            _write(res.image, root / "images" / "all" / name)
            rows.append(
                {
                    "file": name,
                    "source": str(p.relative_to(root)),
                    "sha1": digest,
                    "hard": int(hard),
                    "width": res.image.shape[1],
                    "height": res.image.shape[0],
                }
            )
            stats["pool"] += 1
            stats["hard"] += int(hard)
    for sub in ("pairs", "demo"):
        folder = raw / sub
        if not folder.is_dir():
            continue
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.suffix.lower() in EXTS:
                img = _load(p)
                res = blur_faces(img)
                _write(res.image, root / "images" / sub / f"{p.stem}.jpg")
                stats[sub] += 1
    manifest = root / "manifest.csv"
    with manifest.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["file", "source", "sha1", "hard", "width", "height"]
        )
        writer.writeheader()
        writer.writerows(rows)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--root", default="datasets/vj_items")
    args = ap.parse_args()
    stats = ingest(Path(args.root))
    print(stats)
    if stats["pool"] < 150:
        print(
            f"WARNING: {stats['pool']} photos in the pool; the plan needs >= 150 (about 30 hard)."
        )


if __name__ == "__main__":
    main()
