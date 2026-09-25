#!/usr/bin/env python3
"""Benchmark TrayAgent's OpenCV hot paths on the current machine.

The same script runs on x86 (c7i), on Graviton with stock opencv-python, and on
Graviton with COOL (Cloud-Optimized OpenCV Library). Each run appends one JSON
line to ``--out``. ``--report`` renders all lines into ``reports/cool/RESULTS.md``.

    python benchmarks/cv_bench.py --label c7g.large-stock --out reports/cool/runs.jsonl
    python benchmarks/cv_bench.py --report reports/cool/runs.jsonl

Workloads:
* primitives: ``resize`` (INTER_AREA 4032x3024 → 1024), ``adaptiveThreshold``
  (Gaussian), ``findContours``, ``GaussianBlur``, ``cvtColor`` BGR→HSV, ``warpPerspective``;
* TrayAgent tools: ``assess_quality``, ``rectify_tray`` and ``tile_detect`` (with
  the OpenCV classical detector, or ``--model`` for the ONNX detector).

Inputs are procedurally drawn trays at phone resolution (4032x3024). They are
timing inputs only, and the accuracy of anything on them is irrelevant. The
OpenCV build information is recorded, so a COOL/KleidiCV build is visible in
the report.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))


def _timeit(fn, repeat: int, warmup: int = 2) -> dict[str, float]:
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t) * 1000)
    samples.sort()
    return {
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(samples[min(len(samples) - 1, int(0.95 * len(samples)))], 3),
        "n": repeat,
    }


def build_flags() -> dict[str, object]:
    info = cv2.getBuildInformation()
    lowered = info.lower()
    return {
        "opencv": cv2.__version__,
        "kleidicv": "kleidicv" in lowered,
        "neon": "neon" in lowered,
        "threads": cv2.getNumThreads(),
        "cpu_features": cv2.getCPUFeaturesLine() if hasattr(cv2, "getCPUFeaturesLine") else "",
    }


def run(label: str, repeat: int, model: str | None) -> dict:
    from app.agent.tools import assess_quality, rectify_tray, tile_detect
    from app.services.detector_cv import ClassicalDetector, build_detector
    from tests.fixtures.synth_tray import make_tray

    tray = make_tray(n_items=80, seed=1, size=(3024, 4032), item_radius=(40, 60), perspective=0.08)
    img = tray.image
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(img, (1024, 768), interpolation=cv2.INTER_AREA)
    thr = cv2.adaptiveThreshold(
        cv2.cvtColor(small, cv2.COLOR_BGR2GRAY),
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        5,
    )
    H = cv2.getPerspectiveTransform(
        tray.tray_quad, np.float32([[0, 0], [1599, 0], [1599, 1199], [0, 1199]])
    )
    if model:
        det, status = build_detector("onnx", model_path=model)
        if det is None:
            raise SystemExit(status.reason)
    else:
        det = ClassicalDetector()
    work = cv2.resize(img, (2048, 1536), interpolation=cv2.INTER_AREA)

    results = {
        "resize_area_4032_to_1024": _timeit(
            lambda: cv2.resize(img, (1024, 768), interpolation=cv2.INTER_AREA), repeat
        ),
        "adaptive_threshold_gaussian_1024": _timeit(
            lambda: cv2.adaptiveThreshold(
                cv2.cvtColor(small, cv2.COLOR_BGR2GRAY),
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                31,
                5,
            ),
            repeat,
        ),
        "find_contours_1024": _timeit(
            lambda: cv2.findContours(thr, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE), repeat
        ),
        "gaussian_blur_4032": _timeit(lambda: cv2.GaussianBlur(gray, (9, 9), 0), repeat),
        "cvtcolor_hsv_4032": _timeit(lambda: cv2.cvtColor(img, cv2.COLOR_BGR2HSV), repeat),
        "warp_perspective_to_1600": _timeit(
            lambda: cv2.warpPerspective(img, H, (1600, 1200)), repeat
        ),
        "tool_assess_quality": _timeit(lambda: assess_quality(work), max(3, repeat // 3)),
        "tool_rectify_tray": _timeit(lambda: rectify_tray(work), max(3, repeat // 3)),
        "tool_tile_detect": _timeit(
            lambda: tile_detect(work, det, grid=(2, 3)), max(3, repeat // 5), warmup=1
        ),
    }
    return {
        "label": label,
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "detector": getattr(det, "name", "?"),
        "build": build_flags(),
        "results": results,
    }


def report(runs_path: Path) -> str:
    runs = [json.loads(line) for line in runs_path.read_text().splitlines() if line.strip()]
    if not runs:
        return "# COOL benchmark\n\nNo runs recorded.\n"
    keys = list(runs[0]["results"])
    base = runs[0]
    out = [
        "# OpenCV hot-path benchmark (x86 vs Graviton, with and without COOL)",
        "",
        "Median ms per call (lower is better). The speedup is relative to the first row, "
        f"`{base['label']}`. Inputs are synthetic phone-resolution trays (timing only).",
        "",
        "| Workload | " + " | ".join(r["label"] for r in runs) + " |",
        "|---|" + "---|" * len(runs),
    ]
    for k in keys:
        cells = []
        for r in runs:
            v = r["results"][k]["median_ms"]
            b = base["results"][k]["median_ms"]
            cells.append(f"{v:.2f}" + ("" if r is base else f" ({b / v:.2f}x)"))
        out.append(f"| `{k}` | " + " | ".join(cells) + " |")
    out += ["", "## Runs", ""]
    for r in runs:
        b = r["build"]
        out.append(
            f"- `{r['label']}`: {r['date']}, {r['machine']}, OpenCV {b['opencv']}, "
            f"KleidiCV={b['kleidicv']}, threads={b['threads']}, detector={r['detector']}"
        )
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", default=f"{platform.machine()}-local")
    ap.add_argument("--repeat", type=int, default=30)
    ap.add_argument("--model", default=None)
    ap.add_argument("--out", default="reports/cool/runs.jsonl")
    ap.add_argument("--report", default=None, help="render a runs.jsonl into RESULTS.md")
    args = ap.parse_args()
    if args.report:
        runs_path = Path(args.report)
        target = runs_path.parent / "RESULTS.md"
        target.write_text(report(runs_path))
        print(f"wrote {target}")
        return
    rec = run(args.label, args.repeat, args.model)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(json.dumps(rec["results"], indent=1))


if __name__ == "__main__":
    main()
