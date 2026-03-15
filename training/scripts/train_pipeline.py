#!/usr/bin/env python3
"""One-command training pipeline: validate -> train -> evaluate -> export.

Usage:
    python training/scripts/train_pipeline.py --version v0001
    python training/scripts/train_pipeline.py --version v0002 --epochs 100 --batch 16
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DIVIDER = "=" * 60


def banner(step: int, title: str) -> None:
    print(f"\n{DIVIDER}")
    print(f"  Step {step}: {title}")
    print(DIVIDER)


def run(cmd: list[str], label: str) -> subprocess.CompletedProcess[str]:
    """Run a subprocess, abort pipeline on failure."""
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False, text=True)
    if result.returncode != 0:
        print(f"\n  FAILED at: {label}")
        print(f"  Exit code: {result.returncode}")
        sys.exit(result.returncode)
    return result


def run_capture(cmd: list[str], label: str) -> str:
    """Run a subprocess, stream stderr to console, capture stdout."""
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=None, text=True)
    if result.returncode != 0:
        print(f"\n  FAILED at: {label}")
        sys.exit(result.returncode)
    return result.stdout


def find_run_dir(stdout: str) -> str | None:
    """Extract save_dir from train.py JSON output (multi-line JSON block)."""
    # Strategy: find the JSON block that contains "save_dir"
    # train.py prints a pretty-printed JSON with json.dumps(summary, indent=2)
    lines = stdout.strip().splitlines()

    # Try parsing entire stdout as JSON
    try:
        data = json.loads(stdout)
        if "save_dir" in data:
            return data["save_dir"]
    except (json.JSONDecodeError, TypeError):
        pass

    # Find JSON blocks: scan for lines starting with '{'
    json_blocks: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("{"):
            block_lines = []
            brace_depth = 0
            for j in range(i, len(lines)):
                stripped = lines[j].strip()
                brace_depth += stripped.count("{") - stripped.count("}")
                block_lines.append(stripped)
                if brace_depth == 0:
                    json_blocks.append("\n".join(block_lines))
                    i = j + 1
                    break
            else:
                i += 1
        else:
            i += 1

    # Parse each JSON block, look for save_dir
    for block in reversed(json_blocks):
        try:
            data = json.loads(block)
            if isinstance(data, dict) and "save_dir" in data:
                return data["save_dir"]
        except (json.JSONDecodeError, TypeError):
            continue

    # Last resort: look for run_summary.json in recent outputs
    outputs = Path("outputs/vj_items")
    if outputs.exists():
        summaries = sorted(outputs.rglob("run_summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if summaries:
            try:
                data = json.loads(summaries[0].read_text(encoding="utf-8"))
                return data.get("save_dir")
            except (json.JSONDecodeError, TypeError):
                pass

    return None


def main() -> None:
    p = argparse.ArgumentParser(description="Full training pipeline: validate -> train -> eval -> export")
    p.add_argument("--version", required=True, help="Model version tag (e.g. v0001)")
    p.add_argument("--config", default="training/configs/yolo_v1.yaml", help="Training config file")
    p.add_argument("--dataset-root", default="datasets/vj_items", help="Dataset root directory")
    p.add_argument("--skip-validate", action="store_true", help="Skip dataset validation step")
    p.add_argument("--epochs", type=int, help="Override epochs from config")
    p.add_argument("--batch", type=int, help="Override batch size from config")
    p.add_argument("--imgsz", type=int, help="Override image size from config")
    args = p.parse_args()

    print(f"\n{'#' * 60}")
    print(f"  VietJewelers Training Pipeline")
    print(f"  Version: {args.version}")
    print(f"  Config:  {args.config}")
    print(f"  Dataset: {args.dataset_root}")
    print(f"{'#' * 60}")

    # ── Step 1: Validate Dataset ──────────────────────────────
    if not args.skip_validate:
        banner(1, "Validate Dataset")
        run(
            [sys.executable, "tools/labeling/validate_dataset.py", "--root", args.dataset_root],
            "Dataset validation",
        )
        print("  Dataset validation passed.")
    else:
        print("\n  [Skipped] Dataset validation")

    # ── Step 2: Train ─────────────────────────────────────────
    banner(2, "Train Model")
    train_cmd = [sys.executable, "training/scripts/train.py", "--config", args.config]
    if args.epochs:
        train_cmd += ["--epochs", str(args.epochs)]
    if args.batch:
        train_cmd += ["--batch", str(args.batch)]
    if args.imgsz:
        train_cmd += ["--imgsz", str(args.imgsz)]

    train_stdout = run_capture(train_cmd, "Model training")
    print(train_stdout)

    run_dir = find_run_dir(train_stdout)
    if not run_dir:
        print("  ERROR: Could not determine run directory from train output.")
        print("  Please check training output above.")
        sys.exit(1)
    print(f"  Run directory: {run_dir}")

    # Verify best.pt exists
    best_pt = Path(run_dir) / "weights" / "best.pt"
    if not best_pt.exists():
        print(f"  ERROR: best.pt not found at {best_pt}")
        sys.exit(1)

    # ── Step 3: Evaluate ──────────────────────────────────────
    banner(3, "Evaluate Model")
    run(
        [sys.executable, "training/scripts/eval.py", "--run-dir", run_dir, "--data", f"{args.dataset_root}/data.yaml"],
        "Model evaluation (val+test)",
    )

    # Count accuracy on val split
    print("\n  Count accuracy (val):")
    run(
        [sys.executable, "training/scripts/count_accuracy.py",
         "--run-dir", run_dir, "--split", "val", "--root", args.dataset_root],
        "Count accuracy (val)",
    )

    # Count accuracy on test split (may fail if no test images)
    print("\n  Count accuracy (test):")
    test_result = subprocess.run(
        [sys.executable, "training/scripts/count_accuracy.py",
         "--run-dir", run_dir, "--split", "test", "--root", args.dataset_root],
        capture_output=True, text=True,
    )
    if test_result.returncode != 0:
        print("  WARNING: Test split evaluation skipped (no test images or error)")
    else:
        print(test_result.stdout)

    # ── Step 4: Export ────────────────────────────────────────
    banner(4, "Export Model")
    run(
        [sys.executable, "training/scripts/export.py",
         "--run-dir", run_dir, "--version", args.version, "--dataset-root", args.dataset_root],
        "Model export",
    )

    # ── Step 5: Summary ──────────────────────────────────────
    banner(5, "Summary")
    model_dir = Path("models/vj_items") / args.version
    manifest_path = model_dir / "manifest.json"

    print(f"  Model exported to: {model_dir}")
    print(f"  Files:")
    if model_dir.exists():
        for f in sorted(model_dir.iterdir()):
            size_kb = f.stat().st_size / 1024
            print(f"    {f.name} ({size_kb:.0f} KB)")

    # Show key metrics from manifest
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        metrics = manifest.get("metrics", {})
        val_metrics = metrics.get("val", {})
        if val_metrics:
            print(f"\n  Validation Metrics:")
            print(f"    mAP50:     {val_metrics.get('map50', 'N/A')}")
            print(f"    mAP50-95:  {val_metrics.get('map5095', 'N/A')}")
            print(f"    Precision: {val_metrics.get('precision', 'N/A')}")
            print(f"    Recall:    {val_metrics.get('recall', 'N/A')}")

        count_acc = manifest.get("count_accuracy", {})
        for key, data in count_acc.items():
            if isinstance(data, dict) and "exact_match_rate" in data:
                print(f"\n  Count Accuracy ({data.get('split', key)}):")
                print(f"    Exact match: {data['exact_match_rate']:.1%}" if data['exact_match_rate'] else "    Exact match: N/A")
                print(f"    MAE:         {data.get('mean_absolute_error', 'N/A')}")

    print(f"\n  Next steps:")
    print(f"    1. Set environment variables:")
    print(f"       MODEL_PT_PATH={model_dir / 'best.pt'}")
    if (model_dir / "best.onnx").exists():
        print(f"       MODEL_ONNX_PATH={model_dir / 'best.onnx'}")
    print(f"       MOCK_MODE=false")
    print(f"       MODEL_VERSION={args.version}")
    print(f"    2. Restart backend: make backend-dev")
    print(f"    3. Smoke test: make model-smoke IMAGE=<path_to_test_image>")
    print(f"\n{DIVIDER}")
    print(f"  Pipeline complete!")
    print(DIVIDER)


if __name__ == "__main__":
    main()
