#!/usr/bin/env python3
"""Pre-label tray photos so that humans only *correct* boxes in CVAT.

Backends:
* ``owlv2``: open-vocabulary detection with OWLv2 (google/owlv2-base-patch16-ensemble,
  Apache-2.0) through Hugging Face ``transformers`` (text queries such as "a ring",
  "a pendant", "an earring", "a bracelet"). Needs ``pip install transformers torch``
  and access to huggingface.co. This is the default for real photos.
* ``classical``: the OpenCV 5 baseline detector from the backend. It works offline,
  and is used in tests and as a fallback.

Output: a CVAT "YOLO 1.1" archive (obj.names, obj.data, train.txt,
obj_train_data/*.txt with normalized ``0 cx cy w h`` lines). Pass it to
``cvat_tasks.py create-task --prelabels``. Pre-labels are *never* training labels
until a human has reviewed them in CVAT.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from collections.abc import Iterable
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

QUERIES = [
    "a ring",
    "a pendant",
    "an earring",
    "a necklace",
    "a bracelet",
    "a jewelry item",
]


class ClassicalBackend:
    name = "classical"

    def __init__(self) -> None:
        from app.services.detector_cv import ClassicalDetector

        self.det = ClassicalDetector()

    def boxes(self, img) -> list[tuple[float, float, float, float, float]]:
        return [(d.x, d.y, d.w, d.h, d.conf) for d in self.det.detect(img)]


class Owlv2Backend:  # pragma: no cover - needs model download
    name = "owlv2"

    def __init__(
        self, threshold: float = 0.15, model: str = "google/owlv2-base-patch16-ensemble"
    ):
        from transformers import pipeline

        self.pipe = pipeline("zero-shot-object-detection", model=model)
        self.threshold = threshold

    def boxes(self, img) -> list[tuple[float, float, float, float, float]]:
        from PIL import Image

        from app.services.detector_cv import Det, nms

        rgb = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        out = self.pipe(rgb, candidate_labels=QUERIES, threshold=self.threshold)
        dets = [
            Det(
                o["box"]["xmin"],
                o["box"]["ymin"],
                o["box"]["xmax"] - o["box"]["xmin"],
                o["box"]["ymax"] - o["box"]["ymin"],
                float(o["score"]),
            )
            for o in out
        ]
        return [(d.x, d.y, d.w, d.h, d.conf) for d in nms(dets, self.threshold, 0.5)]


def yolo_lines(
    boxes: Iterable[tuple[float, float, float, float, float]], w: int, h: int
) -> list[str]:
    lines = []
    for x, y, bw, bh, _ in boxes:
        cx, cy = (x + bw / 2) / w, (y + bh / 2) / h
        lines.append(f"0 {cx:.6f} {cy:.6f} {bw / w:.6f} {bh / h:.6f}")
    return lines


def write_cvat_yolo_zip(labels: dict[str, list[str]], out_zip: Path) -> Path:
    """CVAT 'YOLO 1.1' import layout."""
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("obj.names", "item\n")
        zf.writestr(
            "obj.data",
            "classes = 1\ntrain = data/train.txt\nnames = data/obj.names\nbackup = backup/\n",
        )
        zf.writestr(
            "train.txt", "".join(f"data/obj_train_data/{n}\n" for n in sorted(labels))
        )
        for name, lines in sorted(labels.items()):
            zf.writestr(
                f"obj_train_data/{Path(name).stem}.txt",
                "\n".join(lines) + ("\n" if lines else ""),
            )
    return out_zip


def prelabel(images_dir: Path, out_zip: Path, backend) -> dict[str, int]:
    labels: dict[str, list[str]] = {}
    total = 0
    for p in sorted(images_dir.iterdir()):
        if p.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        img = cv2.imread(str(p))
        if img is None:
            continue
        h, w = img.shape[:2]
        lines = yolo_lines(backend.boxes(img), w, h)
        labels[p.name] = lines
        total += len(lines)
    write_cvat_yolo_zip(labels, out_zip)
    return {"images": len(labels), "boxes": total}


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--images", default="datasets/vj_items/images/all")
    ap.add_argument("--out", default="datasets/vj_items/prelabels_yolo11.zip")
    ap.add_argument("--backend", choices=["owlv2", "classical"], default="owlv2")
    ap.add_argument("--threshold", type=float, default=0.15)
    args = ap.parse_args()
    backend = (
        Owlv2Backend(args.threshold) if args.backend == "owlv2" else ClassicalBackend()
    )
    stats = prelabel(Path(args.images), Path(args.out), backend)
    print(f"{backend.name}: {stats} -> {args.out}")


if __name__ == "__main__":
    main()
