#!/usr/bin/env python3
"""Evaluate TrayAgent on the FROZEN real test set (Phase 7).

    python training/scripts/agent_eval.py --root datasets/vj_items \
        --backend onnx --model models/trayagent_v1.onnx --out reports/agentic

What it measures, per test image (ground truth = the human-reviewed CVAT boxes):

* Single shot: the detector once on the full photo (count, and boxes at a low
  score threshold for mAP@0.5).
* Agentic: the full controller (quality → rectify/detect → tile/zoom →
  compare → decision) under three POS regimes:
    - ``pos_correct``: expected = true count (the normal case);
    - ``pos_none``: no POS figure (can the agent auto-accept a wrong count?);
    - ``pos_wrong``: expected = true count + 1 (a stale POS; the agent must
      not auto-accept its own count as the POS count).
* Rates: escalation, recapture, and false auto-accept (auto-accepted with
  count ≠ truth).
* Latency: p50/p95 per run and per single-shot detect, on this machine
  (record the instance type with ``--machine``, e.g. ``c7g.large``).

Honesty guards:
* It refuses to run unless ``split_dataset.py --verify`` passes (the frozen test
  manifest is intact). ``--allow-unfrozen`` exists for smoke tests only, and then
  stamps every output "NOT REPORTABLE".
* ``--synthetic-smoke`` builds a synthetic set in a temp dir to test this script.
  Its output also says "SYNTHETIC — NOT A RESULT", and it refuses to write
  into ``reports/``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "tools" / "labeling"))
sys.path.insert(0, str(REPO))

from app.agent.controller import MemoryEvidenceStore, run_agent  # noqa: E402
from app.agent.policy import Action, PolicyConfig  # noqa: E402
from app.services.detector_cv import build_detector  # noqa: E402
from training.metrics import (
    average_precision,
    count_metrics,
    read_yolo_labels,
)  # noqa: E402

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
REGIMES = ("pos_correct", "pos_none", "pos_wrong")


@dataclass
class Row:
    image: str
    true: int
    single: int
    single_ms: float
    runs: dict = field(default_factory=dict)  # regime -> dict


def percentile(values: list[float], q: float) -> float:
    return float(np.percentile(values, q)) if values else float("nan")


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True
        ).strip()
    except Exception:
        return "unknown"


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def make_detectors(args):
    det, status = build_detector(
        args.backend, model_path=args.model, engine=args.engine, score_thr=args.conf
    )
    if det is None:
        raise SystemExit(f"detector not ready: {status.reason}")
    ap_det = det
    if args.backend == "onnx":  # a low threshold for AP only
        ap_det, _ = build_detector(
            "onnx", model_path=args.model, engine=args.engine, score_thr=0.01
        )
    return det, ap_det, status


def evaluate(root: Path, args, out: Path, reportable: bool, banner: str | None) -> dict:
    det, ap_det, status = make_detectors(args)
    cfg = PolicyConfig()
    test_imgs = sorted(
        p
        for p in (root / "images" / "test").iterdir()
        if p.suffix.lower() in IMAGE_EXTS
    )
    if not test_imgs:
        raise SystemExit("empty test split")
    rows: list[Row] = []
    ap_preds, ap_gts, agent_preds = [], [], []
    evidence_dir = out / "failures"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    finals: dict[str, bytes] = {}
    for i, p in enumerate(test_imgs):
        img = cv2.imread(str(p))
        h, w = img.shape[:2]
        gt = read_yolo_labels(root / "labels" / "test" / f"{p.stem}.txt", w, h)
        t0 = time.perf_counter()
        single = det.detect(img)
        single_ms = (time.perf_counter() - t0) * 1000
        ap_preds.append([(d.x, d.y, d.w, d.h, d.conf) for d in ap_det.detect(img)])
        ap_gts.append(gt)
        row = Row(p.name, len(gt), len(single), single_ms)
        for regime in REGIMES:
            expected = {
                "pos_correct": len(gt),
                "pos_none": None,
                "pos_wrong": len(gt) + 1,
            }[regime]
            store = MemoryEvidenceStore()
            r = run_agent(
                img,
                detector=det,
                expected_count=expected,
                cfg=cfg,
                evidence=store,
                key_prefix=f"e/{i}/{regime}",
            )
            row.runs[regime] = {
                "decision": r.action.value,
                "code": r.code,
                "count": r.count,
                "steps": r.steps_used,
                "ms": r.elapsed_ms,
                "tools": "+".join(e.tool for e in r.trace),
                "flags": ",".join(
                    next(
                        (
                            e.outputs.get("flags", [])
                            for e in r.trace
                            if e.tool == "assess_quality"
                        ),
                        [],
                    )
                ),
            }
            if regime == "pos_correct":
                agent_preds.append(
                    [(d.x, d.y, d.w, d.h, d.conf) for d in r.dets_original]
                )
                if r.evidence_key:
                    finals[p.name] = store.objects[r.evidence_key]
        rows.append(row)
        print(
            f"[{i + 1}/{len(test_imgs)}] {p.name} true={row.true} single={row.single} "
            + " ".join(
                f"{k}={v['decision']}:{v['count']}" for k, v in row.runs.items()
            ),
            flush=True,
        )

    summary = summarize(
        rows,
        ap_preds,
        ap_gts,
        agent_preds,
        status.as_dict(),
        args,
        reportable,
        banner,
        root,
    )
    write_outputs(out, rows, summary, finals, test_imgs, root)
    return summary


def summarize(
    rows, ap_preds, ap_gts, agent_preds, det_status, args, reportable, banner, root
) -> dict:
    true = [r.true for r in rows]
    single = count_metrics([r.single for r in rows], true)
    per_regime = {}
    for regime in REGIMES:
        runs = [r.runs[regime] for r in rows]
        counted = [
            (r.runs[regime]["count"], r.true)
            for r in rows
            if r.runs[regime]["count"] is not None
        ]
        n = len(runs)
        auto = [
            (r.runs[regime], r.true)
            for r in rows
            if r.runs[regime]["decision"] == "auto_accept"
        ]
        per_regime[regime] = {
            "n": n,
            "count": count_metrics([c for c, _ in counted], [t for _, t in counted]),
            "count_coverage": len(counted) / n if n else float("nan"),
            "auto_accept_rate": len(auto) / n if n else float("nan"),
            "escalation_rate": (
                sum(x["decision"] == "escalate" for x in runs) / n
                if n
                else float("nan")
            ),
            "recapture_rate": (
                sum(x["decision"] == "request_recapture" for x in runs) / n
                if n
                else float("nan")
            ),
            "false_auto_accept_rate": (
                sum(x["count"] != t for x, t in auto) / n if n else float("nan")
            ),
            "latency_ms_p50": percentile([x["ms"] for x in runs], 50),
            "latency_ms_p95": percentile([x["ms"] for x in runs], 95),
            "steps_mean": (
                float(np.mean([x["steps"] for x in runs])) if runs else float("nan")
            ),
        }
    manifest = root / "splits" / "test.manifest.sha256"
    return {
        "reportable": reportable,
        "banner": banner,
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": git_commit(),
        "machine": args.machine or platform.machine(),
        "cpu": platform.processor() or platform.machine(),
        "opencv": cv2.__version__,
        "detector": det_status,
        "dnn_engine": args.engine,
        "test_images": len(rows),
        "test_items": int(sum(true)),
        "test_manifest_sha256": sha256_file(manifest) if manifest.exists() else None,
        "map50_single_shot": average_precision(ap_preds, ap_gts, 0.5),
        "map50_agent_final_boxes": average_precision(agent_preds, ap_gts, 0.5),
        "single_shot": single,
        "single_shot_latency_ms_p50": percentile([r.single_ms for r in rows], 50),
        "single_shot_latency_ms_p95": percentile([r.single_ms for r in rows], 95),
        "agentic": per_regime,
        "prd_targets": {"count_accuracy": "70-85% at MVP (PRD section 1.3)"},
    }


def failure_cases(rows: list[Row], k: int = 8) -> list[tuple[Row, str]]:
    scored = []
    for r in rows:
        a = r.runs["pos_correct"]
        why = []
        if a["count"] is not None and a["count"] != r.true:
            why.append(f"agent count off by {a['count'] - r.true:+d}")
        if (
            r.runs["pos_none"]["decision"] == "auto_accept"
            and r.runs["pos_none"]["count"] != r.true
        ):
            why.append("false auto-accept without POS")
        if r.runs["pos_wrong"]["decision"] == "auto_accept":
            why.append("auto-accepted a stale POS figure")
        if a["decision"] == "request_recapture":
            why.append(f"recapture requested ({a['code']})")
        if a["decision"] == "escalate" and a["count"] == r.true:
            why.append("escalated although the count was right (review cost)")
        if r.single != r.true and a["count"] == r.true:
            continue  # the agent fixed it: not a failure
        if why:
            severity = abs(
                (a["count"] if a["count"] is not None else r.single) - r.true
            )
            scored.append(
                (
                    severity + 10 * ("false auto-accept" in " ".join(why)),
                    r,
                    "; ".join(why),
                )
            )
    scored.sort(key=lambda x: -x[0])
    return [(r, why) for _, r, why in scored[:k]]


def fmt(x, pct=False) -> str:
    if x is None or (isinstance(x, float) and x != x):
        return "n/a"
    return (
        f"{100 * x:.1f}%" if pct else (f"{x:.2f}" if isinstance(x, float) else str(x))
    )


def write_outputs(out: Path, rows, summary, finals, test_imgs, root) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "results.csv").open("w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(
            ["image", "true", "single", "single_ms"]
            + [
                f"{g}_{k}"
                for g in REGIMES
                for k in ("decision", "code", "count", "steps", "ms", "tools", "flags")
            ]
        )
        for r in rows:
            wr.writerow(
                [r.image, r.true, r.single, round(r.single_ms, 1)]
                + [
                    r.runs[g][k]
                    for g in REGIMES
                    for k in (
                        "decision",
                        "code",
                        "count",
                        "steps",
                        "ms",
                        "tools",
                        "flags",
                    )
                ]
            )
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    plots(out, rows, summary)

    fails = failure_cases(rows)
    gallery = []
    for r, why in fails:
        data = finals.get(r.image)
        if data is None:
            continue
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        name = f"failures/{Path(r.image).stem}.jpg"
        cv2.imwrite(str(out / name), img)
        gallery.append((r, why, name))

    s, a = summary, summary["agentic"]
    stamp = "" if s["reportable"] else f"\n> **{s['banner']}**\n"
    lines = [
        "# TrayAgent evaluation results",
        stamp,
        f"- Date: {s['date']} · commit `{s['commit']}` · OpenCV {s['opencv']} (DNN engine `{s['dnn_engine']}`)",
        f"- Machine: `{s['machine']}` ({s['cpu']})",
        f"- Detector: `{s['detector']['backend']}` version `{s['detector'].get('version')}` sha256 `{(s['detector'].get('model_sha256') or 'n/a')[:16]}`",
        f"- Test set: {s['test_images']} images, {s['test_items']} items; frozen manifest sha256 `{(s['test_manifest_sha256'] or 'n/a')[:16]}`",
        "",
        "## Detection and counting",
        "",
        "| Metric | Single shot | TrayAgent (POS correct) |",
        "|---|---|---|",
        f"| mAP@0.5 | {fmt(s['map50_single_shot'])} | {fmt(s['map50_agent_final_boxes'])} (final boxes) |",
        f"| Count MAE | {fmt(s['single_shot']['mae'])} | {fmt(a['pos_correct']['count']['mae'])} |",
        f"| Exact-count accuracy | {fmt(s['single_shot']['exact'], True)} | {fmt(a['pos_correct']['count']['exact'], True)} |",
        f"| Within ±1 | {fmt(s['single_shot']['within1'], True)} | {fmt(a['pos_correct']['count']['within1'], True)} |",
        f"| Count accuracy (PRD-style) | {fmt(s['single_shot'].get('count_accuracy'), True)} | {fmt(a['pos_correct']['count'].get('count_accuracy'), True)} |",
        f"| Images with a count | 100% | {fmt(a['pos_correct']['count_coverage'], True)} (the rest: re-shot requested) |",
        "",
        "Agent MAE/accuracy cover images where the agent produced a count. Final-box mAP counts re-shot",
        "requests as misses, because the agent returned no boxes for them.",
        "",
        f"PRD target: count accuracy {s['prd_targets']['count_accuracy']}.",
        "",
        "## Agent decisions",
        "",
        "| POS regime | auto-accept | escalate | re-shot | FALSE auto-accept | steps (mean) | latency p50 / p95 |",
        "|---|---|---|---|---|---|---|",
    ]
    for g in REGIMES:
        x = a[g]
        lines.append(
            f"| `{g}` | {fmt(x['auto_accept_rate'], True)} | {fmt(x['escalation_rate'], True)} | {fmt(x['recapture_rate'], True)} | "
            f"{fmt(x['false_auto_accept_rate'], True)} | {fmt(x['steps_mean'])} | {fmt(x['latency_ms_p50'])} / {fmt(x['latency_ms_p95'])} ms |"
        )
    lines += [
        "",
        f"Single-shot detect latency p50 / p95: {fmt(s['single_shot_latency_ms_p50'])} / {fmt(s['single_shot_latency_ms_p95'])} ms.",
        "",
        "`pos_correct`: expected = truth. `pos_none`: no POS figure. `pos_wrong`: expected = truth + 1 (stale POS).",
        "A false auto-accept is a run the agent accepted without a human whose count differs from the truth.",
        "",
        "Plots: `count_error.png`, `latency.png`, `decisions.png`. Per-image rows: `results.csv`. Raw numbers: `summary.json`.",
        "",
        f"## Failure gallery ({len(gallery)} cases)",
        "",
    ]
    for r, why, name in gallery:
        run = r.runs["pos_correct"]
        lines += [
            f"### {r.image}",
            "",
            f"![{r.image}]({name})",
            "",
            f"- Truth {r.true}, single shot {r.single}, agent {run['count']} ({run['decision']}, `{run['code']}`), quality flags: {run['flags'] or 'none'}",
            f"- Tool path: `{run['tools']}`",
            f"- What went wrong: {why}.",
            "- Analysis (owner or engineer): _fill in after looking at the image_",
            "",
        ]
    (out / "RESULTS.md").write_text("\n".join(lines) + "\n")


def plots(out: Path, rows, summary) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        print("matplotlib not installed: skipping plots")
        return
    err_single = [r.single - r.true for r in rows]
    err_agent = [
        r.runs["pos_correct"]["count"] - r.true
        for r in rows
        if r.runs["pos_correct"]["count"] is not None
    ]
    fig, ax = plt.subplots(figsize=(7, 4), dpi=150)
    lo, hi = (
        min(err_single + err_agent + [0]) - 1,
        max(err_single + err_agent + [0]) + 2,
    )
    bins = np.arange(lo, hi) - 0.5
    ax.hist(err_single, bins=bins, alpha=0.6, label="single shot", color="#8a8f98")
    ax.hist(err_agent, bins=bins, alpha=0.8, label="TrayAgent", color="#2b6cb0")
    ax.set_xlabel("count error (predicted − true)")
    ax.set_ylabel("test images")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "count_error.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4), dpi=150)
    for g, color in zip(REGIMES, ("#2b6cb0", "#8a8f98", "#c05621"), strict=True):
        ms = sorted(r.runs[g]["ms"] for r in rows)
        ax.plot(ms, np.linspace(0, 1, len(ms)), label=g, color=color)
    ax.set_xlabel(f"agent run latency (ms) on {summary['machine']}")
    ax.set_ylabel("share of runs")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "latency.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 3.5), dpi=150)
    decisions = ("auto_accept", "escalate", "request_recapture")
    x = np.arange(len(REGIMES))
    for k, (d, color) in enumerate(
        zip(decisions, ("#2f855a", "#c05621", "#6b46c1"), strict=True)
    ):
        vals = [
            sum(r.runs[g]["decision"] == d for r in rows) / len(rows) for g in REGIMES
        ]
        ax.bar(x + (k - 1) * 0.25, vals, width=0.25, label=d, color=color)
    ax.set_xticks(x, REGIMES)
    ax.set_ylabel("share of runs")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "decisions.png")
    plt.close(fig)


def synthetic_root(tmp: Path) -> Path:
    sys.path.insert(0, str(REPO / "backend"))
    from tests.fixtures.synth_tray import make_tray

    root = tmp / "synth"
    for d in ("images/test", "labels/test"):
        (root / d).mkdir(parents=True, exist_ok=True)
    for i in range(8):
        t = make_tray(
            n_items=8 + i,
            seed=500 + i,
            glare=0.2 if i == 3 else 0.0,
            blur=21 if i == 5 else 0,
        )
        cv2.imwrite(str(root / "images/test" / f"t{i}.jpg"), t.image)
        h, w = t.image.shape[:2]
        (root / "labels/test" / f"t{i}.txt").write_text(
            "".join(
                f"0 {(x + bw / 2) / w} {(y + bh / 2) / h} {bw / w} {bh / h}\n"
                for x, y, bw, bh in t.boxes
            )
        )
    return root


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--root", default="datasets/vj_items")
    ap.add_argument("--backend", default="onnx", choices=["onnx", "classical"])
    ap.add_argument("--model", default="models/trayagent_v1.onnx")
    ap.add_argument("--engine", default="auto", choices=["auto", "new", "classic"])
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--out", default="reports/agentic")
    ap.add_argument(
        "--machine", default=None, help="e.g. c7g.large (recorded in the report)"
    )
    ap.add_argument("--allow-unfrozen", action="store_true")
    ap.add_argument("--synthetic-smoke", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    if args.synthetic_smoke:
        import tempfile

        if "reports" in out.resolve().parts:
            raise SystemExit("synthetic smoke output must not go under reports/")
        root = synthetic_root(Path(tempfile.mkdtemp()))
        summary = evaluate(root, args, out, False, "SYNTHETIC SMOKE TEST: NOT A RESULT")
    else:
        import split_dataset

        root = Path(args.root)
        problems = split_dataset.verify(root)
        if problems and not args.allow_unfrozen:
            raise SystemExit(
                "frozen test set check failed:\n  " + "\n  ".join(problems)
            )
        if args.allow_unfrozen and "reports" in out.resolve().parts:
            raise SystemExit("unfrozen evaluations must not go under reports/")
        banner = (
            None if not problems else "NOT REPORTABLE: test set not frozen/verified"
        )
        summary = evaluate(root, args, out, not problems, banner)
    print(
        json.dumps(
            {k: summary[k] for k in ("reportable", "test_images", "map50_single_shot")},
            default=str,
        )
    )


if __name__ == "__main__":
    main()
