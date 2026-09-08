"""Stage 1 — real pipeline core identity probe (§11-12, §18).

frame pass (real detector + real embeddings, cached) → ambiguity-margin
sweep on TUNE only (frozen) → P1-P4 on OPEN/DENSE/FAR → px-height recall →
ReID diagnostics → compute profile. Detector/embedder are injectable so the
orchestration is testable offline; the Kaggle run uses the real ones.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import yaml

from ml.eval.mot_io import read_mot
from ml.gate0a.cloud import BANNER, cache, reid_diag, variants
from ml.gate0a.cloud.extract_clip import export_clip, slice_gt, slice_keyed
from ml.gate0a.cloud.frame_pass import load_emb, run_frame_pass
from ml.gate0a.cloud.gt_policy import suppress_in_ignore
from ml.gate0a.cloud.report import row_for, write_csv
from ml.gate0a.cloud.stage0 import report_dir
from ml.gate0a.cloud.units import with_percent_fields
from ml.gate0a.runners.px_height_recall import bucket

FINAL = ("OPEN", "DENSE", "FAR")


def _load_state(out_root: Path, name: str) -> dict:
    return json.loads((Path(out_root) / "state" / f"{name}.json").read_text())


def _team_labels(state: dict) -> dict[int, str]:
    p = state.get("gt_team_labels_path")
    if not p or not Path(p).exists():
        return {}
    return {int(k): v for k, v in json.loads(Path(p).read_text()).items()}


def window_inputs(out_root: Path, state: dict, role: str) -> dict:
    """Window-local GT (consider/ignore), detections and cached embeddings."""
    w = state["windows"][role]
    s, e = w["start_frame"], w["end_frame"]
    consider = slice_gt(read_mot(state["gt_consider_path"]), s, e)
    ignore_all = read_mot(state["gt_ignore_path"]) if Path(state["gt_ignore_path"]).exists() else {}
    ignore = slice_gt(ignore_all, s, e)
    wdir = Path(out_root) / "cache" / role
    det = read_mot(wdir / "det.txt") if (wdir / "det.txt").exists() else {}
    det_emb = load_emb(wdir / "det_emb.npz") if (wdir / "det_emb.npz").exists() else {}
    gt_emb = load_emb(wdir / "gt_emb.npz") if (wdir / "gt_emb.npz").exists() else {}
    return {"window": w, "gt": consider, "ignore": ignore, "det": det,
            "det_emb": det_emb, "gt_emb": gt_emb, "dir": wdir}


def run(cfg: dict, contract: dict, out_root: Path, detector_factory, embedder_factory,
        device: str = "cuda") -> dict:
    state = _load_state(out_root, "stage0")
    rep = report_dir(out_root)
    windows = state["windows"]
    gt_all = read_mot(state["gt_consider_path"])
    cache_root = Path(out_root) / "cache"

    # Real inference (cached per window).
    det, det_record = detector_factory()
    emb, reid_record = embedder_factory()
    pass_summary = run_frame_pass(Path(state["video_path"]), windows, gt_all, det, emb,
                                  cache_root, state["video_identity"],
                                  store_dtype=np.float16 if cfg["reid"]["store_dtype"] == "float16" else np.float32)
    (rep / "detector").mkdir(parents=True, exist_ok=True)
    (rep / "detector" / "config.yaml").write_text(yaml.safe_dump({
        "banner": BANNER, "detector": det_record, "tiling": {k: cfg["detector"][k] for k in (
            "tile_px", "overlap_px", "model_input_px", "batch_tiles", "fp16", "nms_iou", "score_floor")},
        "resolution": state.get("resolution")}, sort_keys=False, default_flow_style=False))
    for role in windows:
        if not (cache_root / role / "det.txt").exists():
            raise RuntimeError(f"frame pass produced no cache for {role} — fail closed")

    if cfg["storage"].get("export_clips"):
        clips_dir = Path(out_root) / "clips"
        for role, w in windows.items():
            out = clips_dir / f"{state['dataset_revision'][:8]}_{role}.mp4"
            if not out.exists():
                res = export_clip(Path(state["video_path"]), w["start_frame"], w["end_frame"], out)
                (cache_root / role / "clip_export.json").write_text(json.dumps(res) + "\n")

    tb, grid = cfg["tracker"], list(cfg["tracker"]["ambiguity_margin_grid"])
    offline_cfg = dict(cfg["offline"])
    ign_iou = float(cfg["gt"]["ignore_suppress_iou"])
    team_labels = _team_labels(state)

    # Ambiguity-margin selection on TUNE only (frozen once).
    frozen_path = rep / "real" / "frozen_tracker_config.json"
    frozen_path.parent.mkdir(parents=True, exist_ok=True)
    if frozen_path.exists():
        selected = float(json.loads(frozen_path.read_text())["ambiguity_margin"])
        sweep_rows = json.loads(frozen_path.read_text()).get("sweep", [])
    elif "TUNE" in windows:
        t = window_inputs(out_root, state, "TUNE")
        sweep_rows, selected = variants.sweep_margin(t["gt"], t["ignore"], t["det"], t["det_emb"],
                                                     tb, grid, offline_cfg, ign_iou)
        frozen_path.write_text(json.dumps({"banner": BANNER, "ambiguity_margin": selected,
                                           "rule": contract["tracker_tuning"]["selection_rule"],
                                           "sweep": sweep_rows}, indent=2, default=str) + "\n")
    else:
        selected, sweep_rows = float(grid[-1]), []
        frozen_path.write_text(json.dumps({"banner": BANNER, "ambiguity_margin": selected,
                                           "rule": "no TUNE window — default"}, indent=2) + "\n")
    if sweep_rows:
        write_csv([with_percent_fields({"clip": "TUNE", **r}) for r in sweep_rows],
                  rep / "real" / "margin_sweep.csv")

    # P1-P4 (+ P4_noteam) on the three frozen clips.
    results: dict[str, dict[str, dict]] = {}
    rows = []
    for role in FINAL:
        x = window_inputs(out_root, state, role)
        results[role] = {}
        for name in variants.REAL:
            m = variants.run_variant(variants.VARIANTS[name], x["gt"], x["ignore"], x["det"],
                                     x["det_emb"], None, tb, selected, offline_cfg, ign_iou,
                                     gt_team=team_labels or None)
            results[role][name] = m
            rows.append(row_for(role, m))
    write_csv(rows, rep / "real" / "pipeline_ablation.csv")
    (rep / "real" / "pipeline_ablation.json").write_text(json.dumps(results, indent=2, default=str) + "\n")

    # px-height → recall (per clip + combined), detector outputs suppressed in ignore regions.
    bins = list(contract["px_height_bins"])
    pr_rows, combined_gt, combined_det = [], {}, {}
    offset = 0
    for role in FINAL:
        x = window_inputs(out_root, state, role)
        dets = suppress_in_ignore(x["det"], x["ignore"], ign_iou)
        for r in bucket(x["gt"], dets, bins):
            pr_rows.append({"clip": role, **r})
        for f, v in x["gt"].items():
            combined_gt[f + offset] = v
        for f, v in dets.items():
            combined_det[f + offset] = v
        offset += x["window"]["end_frame"] - x["window"]["start_frame"] + 1
    comb = bucket(combined_gt, combined_det, bins)
    for r in comb:
        pr_rows.append({"clip": "COMBINED", **r})
    ge40 = [(r["n_gt"], r["recall"]) for r in comb if r["bin_lo_px"] >= 40 and r["n_gt"]]
    recall40 = round(sum(n * float(rc) for n, rc in ge40) / sum(n for n, _ in ge40), 4) if ge40 else None
    with open(rep / "detector" / "px_height_recall.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["clip", *comb[0].keys(), "recall_percent"])
        w.writeheader()
        for r in pr_rows:
            w.writerow({**r, "recall_percent": round(float(r["recall"]) * 100, 2) if r["recall"] != "" else ""})
    _plot_recall(comb, rep / "detector" / "px_height_recall.png")

    # ReID diagnostics on GT crops (evaluation only) per clip + pooled summary.
    rd: dict = {"banner": BANNER, "per_clip": {}}
    for role in FINAL:
        x = window_inputs(out_root, state, role)
        rd["per_clip"][role] = reid_diag.diagnostics(
            x["gt"], x["gt_emb"], team_labels or None, list(cfg["reid_diag"]["deltas_frames"]),
            int(cfg["reid_diag"]["max_queries"]), int(cfg["seeds"]["global"]))
    rd["pooled"] = _pool_reid(rd["per_clip"])
    (rep / "reid").mkdir(parents=True, exist_ok=True)
    (rep / "reid" / "metrics.json").write_text(json.dumps(rd, indent=2, default=str) + "\n")
    _reid_csv(rd, rep / "reid" / "distance_summary.csv")

    # Compute profile (measured; extrapolations labeled).
    prof = {"banner": BANNER, "gpu": {k: det_record.get(k) for k in ("device", "precision")},
            "frame_pass": pass_summary, "runtime": _runtime()}
    dp = pass_summary.get("detector_profile") or {}
    if dp.get("detector_fps_measured"):
        full_half_frames = int(state["n_video_frames"])
        prof["EXTRAPOLATED_full_half_detector_hours"] = round(
            full_half_frames / dp["detector_fps_measured"] / 3600, 2)
        prof["EXTRAPOLATED_note"] = "linear extrapolation from measured detector fps; NOT measured"
    (rep / "compute").mkdir(parents=True, exist_ok=True)
    (rep / "compute" / "profile.json").write_text(json.dumps(prof, indent=2, default=str) + "\n")

    st = {"selected_margin": selected, "sweep": sweep_rows, "results": results,
          "recall_ge40": recall40, "px_recall_combined": comb, "reid": rd,
          "detector": det_record, "reid_record": reid_record, "pass_summary": pass_summary,
          "compute": prof, "chain_ran": all(
              (cache_root / r / "det.txt").exists() and (cache_root / r / "det_emb.npz").exists()
              for r in FINAL) and all("P4" in results[r] for r in FINAL)}
    (Path(out_root) / "state" / "stage1.json").write_text(json.dumps(st, indent=2, default=str) + "\n")
    return st


def _runtime() -> dict:
    from ml.gate0a.cloud.artifact_manifest import gpu_info

    return gpu_info()


def _pool_reid(per_clip: dict) -> dict:
    keys = ("top1_retrieval", "within_team_top1_retrieval")
    pooled: dict = {}
    for k in keys:
        acc: dict[str, list[float]] = {}
        for r in per_clip.values():
            for d, v in (r.get(k) or {}).items():
                if v is not None:
                    acc.setdefault(d, []).append(float(v))
        pooled[k] = {d: round(float(np.mean(v)), 4) for d, v in acc.items()}
    seps = [r.get("separation_same_player_vs_same_team_other") for r in per_clip.values()]
    seps = [s for s in seps if s is not None]
    pooled["separation_same_player_vs_same_team_other"] = round(float(np.mean(seps)), 4) if seps else None
    return pooled


def _reid_csv(rd: dict, path: Path) -> None:
    rows = []
    for clip, r in rd["per_clip"].items():
        for name in ("different_player_same_frame", "same_team_different_player", "cross_team_different_player"):
            s = r.get(name) or {}
            rows.append({"clip": clip, "distribution": name, **{k: s.get(k) for k in ("n", "mean", "p10", "p50", "p90")}})
        for d, s in (r.get("same_player_distance") or {}).items():
            rows.append({"clip": clip, "distribution": f"same_player_{d}", **{k: s.get(k) for k in ("n", "mean", "p10", "p50", "p90")}})
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["clip", "distribution", "n", "mean", "p10", "p50", "p90"])
        w.writeheader()
        w.writerows(rows)


def _plot_recall(comb: list[dict], path: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:  # pragma: no cover
        return
    xs = [f"{r['bin_lo_px']}-{r['bin_hi_px'] or '∞'}" for r in comb]
    ys = [float(r["recall"]) if r["recall"] != "" else 0.0 for r in comb]
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.bar(xs, ys, color="#4c72b0")
    ax.set_ylim(0, 1)
    ax.set_ylabel("recall (fraction)")
    ax.set_xlabel("GT bbox height (px)")
    ax.set_title("Detector recall by GT bbox height — DIAGNOSTIC, VAL clips only")
    for i, r in enumerate(comb):
        ax.text(i, ys[i] + 0.02, f"n={r['n_gt']}", ha="center", fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def cache_status(out_root: Path, roles) -> dict:
    root = Path(out_root) / "cache"
    return {r: cache.SKIP if (root / r / "frame_pass.cache.json").exists() else cache.RECOMPUTE for r in roles}


def local_gt_for(out_root: Path, state: dict, role: str) -> dict:
    return window_inputs(out_root, state, role)["gt"]


def det_emb_for(out_root: Path, role: str, s: int, e: int) -> dict:
    return slice_keyed(load_emb(Path(out_root) / "cache" / role / "det_emb.npz"), s, e, renumber=False)
