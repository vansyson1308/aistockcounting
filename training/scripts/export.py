#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ultralytics import YOLO


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def dataset_hash(dataset_root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(dataset_root.rglob("*.txt")):
        h.update(p.relative_to(dataset_root).as_posix().encode("utf-8"))
        h.update(p.read_bytes())
    return h.hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--dataset-root", default="datasets/vj_items")
    args = p.parse_args()

    run_dir = Path(args.run_dir)
    best_pt = run_dir / "weights" / "best.pt"
    if not best_pt.exists():
        raise SystemExit(f"Missing best.pt in {best_pt}")

    out = Path("models/vj_items") / args.version
    out.mkdir(parents=True, exist_ok=True)
    dst_pt = out / "best.pt"
    shutil.copy2(best_pt, dst_pt)

    onnx_path = out / "best.onnx"
    onnx_exported = False
    onnx_error = None
    try:
      model = YOLO(str(dst_pt))
      model.export(format="onnx")
      produced = dst_pt.with_suffix(".onnx")
      if produced.exists():
          shutil.move(str(produced), onnx_path)
          onnx_exported = True
    except Exception as exc:
      onnx_error = str(exc)

    eval_metrics = {}
    eval_file = run_dir / "eval_metrics.json"
    if eval_file.exists():
        eval_metrics = json.loads(eval_file.read_text(encoding="utf-8"))

    count_metrics = {}
    for fn in ["count_accuracy_val.json", "count_accuracy_test.json"]:
        f = run_dir / fn
        if f.exists():
            count_metrics[fn] = json.loads(f.read_text(encoding="utf-8"))

    git_sha = None
    try:
        git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        git_sha = "unknown"

    manifest = {
        "version": args.version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha,
        "source_run_dir": str(run_dir),
        "artifacts": {
            "best_pt": "best.pt",
            "best_pt_sha256": sha256_file(dst_pt),
            "best_onnx": "best.onnx" if onnx_exported else None,
            "onnx_exported": onnx_exported,
            "onnx_error": onnx_error,
        },
        "metrics": eval_metrics,
        "count_accuracy": count_metrics,
        "dataset_hash": dataset_hash(Path(args.dataset_root)),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
