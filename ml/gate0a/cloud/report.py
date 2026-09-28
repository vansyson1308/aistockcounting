"""Report writers: ablation CSVs, oracle-vs-real summaries, executive report.

Every rate metric is written as a fraction with a `_percent` twin (units.py).
Every document starts with the diagnostic banner.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ml.gate0a.cloud import BANNER
from ml.gate0a.cloud.units import with_percent_fields

COLUMNS = ["clip", "variant", "hota", "deta", "assa", "idf1", "id_switches",
           "fragmentation", "completeness", "identity_integrity", "n_detections",
           "n_tracklets", "ambiguity_events", "offline_merges_accepted",
           "offline_merges_rejected", "offline_conflicts", "team_accuracy",
           "team_cluster_margin"]


def row_for(clip: str, m: dict) -> dict:
    r = {"clip": clip, "variant": m.get("variant"),
         "hota": m.get("hota"), "deta": m.get("deta"), "assa": m.get("assa"),
         "idf1": m.get("idf1"), "id_switches": m.get("id_switches"),
         "fragmentation": m.get("mean_pred_ids_per_gt_track"),
         "completeness": m.get("completeness"),
         "identity_integrity": m.get("identity_integrity"),
         "n_detections": m.get("n_detections"), "n_tracklets": m.get("n_tracklets"),
         "ambiguity_events": m.get("ambiguity_events"),
         "offline_merges_accepted": m.get("offline_merges_accepted"),
         "offline_merges_rejected": m.get("offline_merges_rejected"),
         "offline_conflicts": m.get("offline_conflicts"),
         "team_accuracy": m.get("team_accuracy"),
         "team_cluster_margin": m.get("team_cluster_margin")}
    return with_percent_fields(r)


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = COLUMNS + [k for k in (rows[0].keys() if rows else []) if k not in COLUMNS]
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in keys})


def oracle_vs_real(results: dict[str, dict[str, dict]]) -> list[dict]:
    out = []
    for clip, variants in results.items():
        o3, p4 = variants.get("O3"), variants.get("P4")
        if not o3 or not p4:
            continue
        row = {"clip": clip}
        for k in ("hota", "deta", "assa", "idf1", "identity_integrity"):
            row[f"oracle_ceiling_{k}"] = o3.get(k)
            row[f"real_final_{k}"] = p4.get(k)
            row[f"gap_{k}"] = (round(float(o3[k]) - float(p4[k]), 4)
                               if o3.get(k) is not None and p4.get(k) is not None else None)
        out.append(row)
    return out


def _fmt(v, pct: bool = True) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, float) and pct:
        return f"{v * 100:.1f}"
    return str(v)


def md_table(rows: list[dict], cols: list[tuple[str, str]], pct_keys: set[str]) -> str:
    head = "| " + " | ".join(h for _k, h in cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    lines = [head, sep]
    for r in rows:
        lines.append("| " + " | ".join(_fmt(r.get(k), k in pct_keys) for k, _h in cols) + " |")
    return "\n".join(lines)


def executive_report(ctx: dict) -> str:
    """Assemble the Markdown executive report from the run context dict."""
    L: list[str] = []
    L += ["# Gate 0A Cloud — Stage 0+1+2 Executive Report", "", "```", BANNER, "```", ""]
    m = ctx.get("maturity", {})
    L += ["## Maturity result", "", "```",
          f"MATURITY:\n{m.get('maturity', 'not decided')}", "",
          f"EVIDENCE:\n{m.get('summary', '')}", "```", ""]
    if m.get("missing"):
        L += ["Unmet level-2 checks: " + ", ".join(m["missing"]), ""]
    L += ["## Run identity", ""]
    man = ctx.get("manifest", {})
    L += [f"- repo sha: `{man.get('repo_sha')}`",
          f"- diagnostic contract sha256: `{man.get('diagnostic_contract_sha256')}`",
          f"- dataset: {json.dumps(man.get('dataset', {}), default=str)[:400]}",
          f"- clip manifest sha256: `{man.get('clip_manifest_sha256')}`",
          f"- detector: {man.get('detector', {}).get('hf_id')} (revision {man.get('detector', {}).get('revision')}, "
          f"weights sha256 {str(man.get('detector', {}).get('weights_sha256'))[:16]}…, "
          f"{man.get('detector', {}).get('provenance_class')})",
          f"- ReID: {man.get('reid', {}).get('name')} ({man.get('reid', {}).get('provenance_class')})",
          f"- GPU: {man.get('runtime', {}).get('gpu_name')} {man.get('runtime', {}).get('vram_gb')} GB; "
          f"torch {man.get('runtime', {}).get('torch')} / CUDA {man.get('runtime', {}).get('cuda_version')}",
          ""]
    inv = ctx.get("stage0", {})
    L += ["## Stage 0 — data inventory & integrity", ""]
    for k in ("dataset_revision", "gt_path", "video_path", "gt_scope", "video_scope",
              "video_bytes", "download_total_bytes", "fps", "resolution", "n_video_frames",
              "gt_stats", "alignment", "evaluator_units", "sanity_all_passed", "gsr_link"):
        if k in inv:
            L.append(f"- {k}: `{json.dumps(inv[k], default=str)[:600]}`")
    L.append("")
    L += ["## Frozen diagnostic windows (GT-only, pre-prediction)", ""]
    wins = ctx.get("windows", {})
    wrows = [{"role": r, **w} for r, w in wins.items()]
    L.append(md_table(wrows, [("role", "role"), ("start_frame", "start"), ("end_frame", "end"),
                              ("start_s", "start s"), ("end_s", "end s"),
                              ("mean_overlap_pairs", "mean overlap pairs"),
                              ("peak_crowd_size", "peak crowd"), ("median_bbox_h", "median bbox h px"),
                              ("mean_gt_boxes", "mean GT boxes")], set()))
    L.append("")
    if ctx.get("margin_sweep"):
        L += ["## Tracker ambiguity-margin sweep (TUNE only, P2)", ""]
        L.append(md_table(ctx["margin_sweep"], [("ambiguity_margin", "margin"), ("assa", "AssA %"),
                                                 ("hota", "HOTA %"), ("id_switches", "IDSW"),
                                                 ("mean_pred_ids_per_gt_track", "frag"),
                                                 ("completeness", "completeness %")],
                          {"assa", "hota", "completeness"}))
        L += ["", f"Selected margin (frozen before OPEN/DENSE/FAR): **{ctx.get('selected_margin')}**", ""]
    L += ["## Detector — px-height → recall (all clips combined)", ""]
    pr = ctx.get("px_recall_combined", [])
    L.append(md_table(pr, [("bin_lo_px", "lo px"), ("bin_hi_px", "hi px"), ("n_gt", "GT"),
                           ("recall", "recall %"), ("score_mean", "score mean")], {"recall"}))
    L += ["", f"Recall for GT boxes ≥ 40 px (combined): **{_fmt(ctx.get('recall_ge40'))}%**", ""]
    L += ["## ReID diagnostics (GT crops, evaluation only)", "", "```",
          json.dumps(ctx.get("reid_diag", {}), indent=1)[:3000], "```", ""]
    cols = [("clip", "Clip"), ("variant", "Pipeline"), ("hota", "HOTA %"), ("deta", "DetA %"),
            ("assa", "AssA %"), ("idf1", "IDF1 %"), ("id_switches", "IDSW"),
            ("fragmentation", "Frag"), ("completeness", "Compl %"), ("identity_integrity", "Integrity %")]
    pct = {"hota", "deta", "assa", "idf1", "completeness", "identity_integrity"}
    L += ["## Real pipeline P1-P4 (autonomous; GT for scoring only)", ""]
    L.append(md_table(ctx.get("real_rows", []), cols, pct))
    L += ["", "## Oracle O1-O4 (GT boxes, identities hidden; O4 = ORACLE TEAM UPPER BOUND)", ""]
    L.append(md_table(ctx.get("oracle_rows", []), cols, pct))
    L += ["", "## Oracle ceiling vs real final (O3 vs P4)", ""]
    L.append(md_table(ctx.get("gap_rows", []), [("clip", "Clip"), ("oracle_ceiling_hota", "O3 HOTA %"),
                                                 ("real_final_hota", "P4 HOTA %"), ("gap_hota", "gap"),
                                                 ("oracle_ceiling_assa", "O3 AssA %"), ("real_final_assa", "P4 AssA %"),
                                                 ("gap_assa", "gap"), ("oracle_ceiling_identity_integrity", "O3 integ %"),
                                                 ("real_final_identity_integrity", "P4 integ %")],
                      {"oracle_ceiling_hota", "real_final_hota", "gap_hota", "oracle_ceiling_assa",
                       "real_final_assa", "gap_assa", "oracle_ceiling_identity_integrity",
                       "real_final_identity_integrity"}))
    b = ctx.get("bottleneck", {})
    L += ["", "## Bottleneck diagnosis", "", f"**Dominant: {b.get('dominant')}**", "", "```",
          json.dumps({k: v for k, v in b.items() if k != "labels_vocabulary"}, indent=1)[:4000], "```", ""]
    L += ["## Compute profile (MEASURED on this run)", "", "```",
          json.dumps(ctx.get("compute", {}), indent=1)[:2500], "```", ""]
    L += ["## Evidence quality / limitations", ""]
    for note in ctx.get("limitations", []):
        L.append(f"- {note}")
    L += ["", "## Recommended next stage", "", ctx.get("recommendation", ""), ""]
    L += ["---", "", BANNER.replace("\n", " · ")]
    return "\n".join(L) + "\n"


def recommendation(maturity: dict, bottleneck: dict) -> str:
    lvl = maturity.get("maturity", "")
    dom = bottleneck.get("dominant", "UNDETERMINED")
    if lvl.startswith("LEVEL 2"):
        if dom == "DETECTION-LIMITED":
            return ("Stage 3 (detector comparison / short TRAIN-only fine-tune) is justified: "
                    "association machinery is healthy given boxes; detection is the buyable deficit.")
        if dom in ("REID-LIMITED", "ASSOCIATION-LIMITED", "MIXED"):
            return (f"Level 2 reached but the dominant limitation is {dom}: recommend a targeted "
                    "ReID/association iteration on the same frozen clips BEFORE Stage 3; Stage 4 only "
                    "after that iteration shows headroom.")
        return "Level 2 reached with no dominant bottleneck: Stage 4 (medium-horizon on VAL) is justified."
    if lvl.startswith("LEVEL 1.5"):
        return (f"Real pipeline runs but misses level-2 bars; dominant limitation {dom}. Do NOT start "
                "Stage 3/4: fix the named bottleneck on the same clips first (owner decision).")
    return "Real chain did not execute end-to-end; resolve the execution blocker before any further stage."
