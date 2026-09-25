#!/usr/bin/env python3
"""Export a TrayAgent trace as a judge-readable demonstration.

It shows, step by step, how an OpenCV output changed the next tool call,
action or human-approval request (the Agentic Vision criterion).

    # from a deployed or local stack (the real demo tray C):
    python scripts/export_trace_demo.py api --base-url https://dxxx.cloudfront.net --scan-id <uuid>
    # offline, running the agent in-process on local photos:
    python scripts/export_trace_demo.py offline --image C_dense.jpg --previous C_prev.jpg --pos 40

Writes ``docs/competition/trace_demo/`` containing ``trace.json``,
``evidence/NN_tool.jpg`` and ``TRACE_DEMO.md``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "competition" / "trace_demo"

KEYS = {
    "assess_quality": ["blur_var", "glare_ratio", "tray_coverage", "flags"],
    "reduce_glare": ["glare_before", "glare_after"],
    "rectify_tray": ["found", "method", "out_size"],
    "detect": ["count", "mean_conf", "uncertain", "median_box_frac", "crowding"],
    "tile_detect": ["count", "grid", "disagreement_cells"],
    "zoom_recount": ["count_before", "count", "unresolved"],
    "compare_previous": ["aligned", "method", "inliers", "changed_ratio", "changed_regions"],
    "render_evidence": ["boxes", "uncertain_regions", "changed_regions"],
    "planner": ["error"],
}


def summarize_outputs(tool: str, out: dict) -> str:
    parts = []
    for k in KEYS.get(tool, []):
        if k not in out:
            continue
        v = out[k]
        if isinstance(v, float):
            v = round(v, 4)
        if isinstance(v, list) and len(v) > 4:
            v = f"{len(v)} items"
        parts.append(f"{k}={v}")
    return ", ".join(parts)


def write_demo(steps: list[dict], images: dict[int, bytes], meta: dict) -> Path:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "evidence").mkdir(parents=True)
    rows = []
    for s in steps:
        img_rel = None
        if s["seq"] in images:
            img_rel = f"evidence/{s['seq']:02d}_{s['tool']}.jpg"
            (OUT / img_rel).write_bytes(images[s["seq"]])
        rows.append({**s, "evidence_file": img_rel})
    (OUT / "trace.json").write_text(json.dumps({"meta": meta, "steps": rows}, indent=2, default=str) + "\n")

    lines = [
        "# Trace demonstration: OpenCV output drives the agent's next action",
        "",
        f"> Source: {meta['source']}",
        "",
        f"Final decision: **{rows[-1]['decision']}**. {rows[-1]['reason']}",
        "",
        "| # | Step | Tool (OpenCV 5) | Key outputs | Decision it led to | Why (the policy's reason) | ms | Evidence |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        ev = f"[img]({r['evidence_file']})" if r["evidence_file"] else ""
        lines.append(
            f"| {r['seq']} | {r['step_no'] or 'final'} | `{r['tool']}` | {summarize_outputs(r['tool'], r['outputs'])} "
            f"| `{r['decision']}` | {r['reason']} | {r['latency_ms']} | {ev} |"
        )
    lines += ["", "## Causal chain", ""]
    prev_decision = None
    for r in rows:
        if r["decision"] != prev_decision:
            lines.append(f"1. **{r['decision']}**: {r['reason']}")
            prev_decision = r["decision"]
    lines += [
        "",
        "Each reason quotes the OpenCV measurement that triggered the next action (for",
        "example the glare ratio, the crowding, uncertain regions, or the count vs POS).",
        "The last step is always `render_evidence`: the annotated sheet a human approves from.",
    ]
    (OUT / "TRACE_DEMO.md").write_text("\n".join(lines) + "\n")
    return OUT


def from_api(args) -> None:
    import httpx

    headers = {"X-TENANT-KEY": args.tenant} if args.tenant else {}
    base = args.base_url.rstrip("/")
    with httpx.Client(timeout=60, headers=headers) as c:
        data = c.get(f"{base}/api/v1/scans/{args.scan_id}/trace").json()["data"]
        steps = data["steps"]
        images = {s["seq"]: c.get(base + s["evidence_url"]).content for s in steps if s.get("evidence_url")}
    meta = {
        "source": f"{base} scan {args.scan_id} (tray {data['scan']['tray_code']}, POS {data['scan']['expected_count']})",
        "scan": data["scan"],
    }
    print(write_demo(steps, images, meta))


def offline(args) -> None:
    sys.path.insert(0, str(REPO / "backend"))
    import cv2

    from app.agent.controller import MemoryEvidenceStore, run_agent
    from app.services.detector_cv import build_detector

    det, status = build_detector(args.backend, model_path=args.model)
    if det is None:
        raise SystemExit(status.reason)
    img = cv2.imread(args.image)
    prev = cv2.imread(args.previous) if args.previous else None
    store = MemoryEvidenceStore()
    r = run_agent(img, detector=det, expected_count=args.pos, previous_image=prev, evidence=store,
                  key_prefix="evidence/demo", previous_ref=Path(args.previous).name if args.previous else None)
    steps = [e.as_dict() for e in r.trace]
    images = {e.seq: store.objects[e.evidence_key] for e in r.trace if e.evidence_key}
    label = args.label or f"offline run on {Path(args.image).name} (detector: {status.backend})"
    print(write_demo(steps, images, {"source": label, "summary": r.summary()}))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    a = sub.add_parser("api")
    a.add_argument("--base-url", required=True)
    a.add_argument("--scan-id", required=True)
    a.add_argument("--tenant", default=None)
    o = sub.add_parser("offline")
    o.add_argument("--image", required=True)
    o.add_argument("--previous", default=None)
    o.add_argument("--pos", type=int, default=None)
    o.add_argument("--backend", default="onnx", choices=["onnx", "classical"])
    o.add_argument("--model", default=str(REPO / "models" / "trayagent_v1.onnx"))
    o.add_argument("--label", default=None)
    args = ap.parse_args()
    from_api(args) if args.mode == "api" else offline(args)


if __name__ == "__main__":
    main()
