#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml
from ultralytics import YOLO


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="training/configs/yolo_v1.yaml")
    p.add_argument("--epochs", type=int)
    p.add_argument("--imgsz", type=int)
    p.add_argument("--batch", type=int)
    args = p.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    if args.epochs:
        cfg["epochs"] = args.epochs
    if args.imgsz:
        cfg["imgsz"] = args.imgsz
    if args.batch:
        cfg["batch"] = args.batch

    model = YOLO(cfg["model"])
    results = model.train(
        data=cfg["data"],
        epochs=cfg["epochs"],
        imgsz=cfg["imgsz"],
        batch=cfg["batch"],
        seed=cfg.get("seed", 42),
        project=cfg.get("project", "outputs/vj_items"),
        name=cfg.get("name", "train"),
        workers=cfg.get("workers", 4),
        patience=cfg.get("patience", 20),
        device=cfg.get("device", "cpu"),
    )

    save_dir = Path(results.save_dir)
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": cfg,
        "save_dir": str(save_dir),
        "best": str(save_dir / "weights" / "best.pt"),
        "last": str(save_dir / "weights" / "last.pt"),
    }
    (save_dir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
