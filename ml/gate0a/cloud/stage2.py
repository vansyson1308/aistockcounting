"""Stage 2 — Oracle vs Real bottleneck decomposition (§13-16, §23).

O1-O3 (+O4 labeled upper bound) from the cached GT-box embeddings, gap
tables, evidence-based bottleneck classification, the diagnostic maturity
decision, the artifact manifest, and the executive report.
"""

from __future__ import annotations

import json
from pathlib import Path

from ml.gate0a.cloud import BANNER, bottleneck, variants
from ml.gate0a.cloud.artifact_manifest import build_manifest, now_iso, write_manifest
from ml.gate0a.cloud.contract import Evidence, decide_maturity
from ml.gate0a.cloud.report import (
    executive_report,
    oracle_vs_real,
    recommendation,
    row_for,
    write_csv,
)
from ml.gate0a.cloud.stage0 import report_dir
from ml.gate0a.cloud.stage1 import FINAL, _load_state, _team_labels, window_inputs
from ml.gate0a.cloud.units import with_percent_fields


def run(cfg: dict, contract: dict, out_root: Path, repo_root: Path, started_at: str) -> dict:
    s0, s1 = _load_state(out_root, "stage0"), _load_state(out_root, "stage1")
    rep = report_dir(out_root)
    tb, offline_cfg = cfg["tracker"], dict(cfg["offline"])
    ign_iou = float(cfg["gt"]["ignore_suppress_iou"])
    margin = float(s1["selected_margin"])
    team_labels = _team_labels(s0)

    results: dict[str, dict[str, dict]] = {r: dict(v) for r, v in s1["results"].items()}
    orows = []
    for role in FINAL:
        x = window_inputs(out_root, s0, role)
        for name in variants.ORACLE:
            spec = variants.VARIANTS[name]
            if name == "O4" and not team_labels:
                continue
            m = variants.run_variant(spec, x["gt"], x["ignore"], None, None, x["gt_emb"], tb,
                                     margin, offline_cfg, ign_iou, gt_team=team_labels or None)
            results[role][name] = m
            orows.append(row_for(role, m))
    (rep / "oracle").mkdir(parents=True, exist_ok=True)
    write_csv(orows, rep / "oracle" / "oracle_ablation.csv")
    (rep / "oracle" / "oracle_ablation.json").write_text(
        json.dumps({r: {k: v for k, v in results[r].items() if k in variants.ORACLE} for r in FINAL},
                   indent=2, default=str) + "\n")
    gap_rows = [with_percent_fields(r, tuple(k for k in r if k != "clip")) for r in oracle_vs_real(results)]
    write_csv(gap_rows, rep / "oracle" / "oracle_vs_real.csv")

    rules = contract["bottleneck_rules"]
    per_clip = {}
    for role in FINAL:
        per_clip[role] = bottleneck.classify_clip(
            results[role], s1.get("recall_ge40"), (s1.get("reid") or {}).get("per_clip", {}).get(role),
            rules, float(contract["level2_criteria"]["deta_min"]),
            float(contract["level2_criteria"]["recall_ge40px_min"]))
    diag = bottleneck.classify(per_clip)
    diag["banner"] = BANNER
    (rep / "bottleneck").mkdir(parents=True, exist_ok=True)
    (rep / "bottleneck" / "diagnosis.json").write_text(json.dumps(diag, indent=2, default=str) + "\n")
    (rep / "bottleneck" / "diagnosis.md").write_text(_diag_md(diag))

    ev = Evidence(
        chain_ran_end_to_end=bool(s1.get("chain_ran")),
        clips_scored=[r for r in FINAL if "P4" in results.get(r, {})],
        open_p4_hota=results.get("OPEN", {}).get("P4", {}).get("hota"),
        open_p4_deta=results.get("OPEN", {}).get("P4", {}).get("deta"),
        recall_ge40px_combined=s1.get("recall_ge40"),
        bottleneck_label=diag["dominant"],
        notes=["all rates are fractions (evaluator units verified at Stage 0)"],
    )
    maturity = decide_maturity(contract, ev)
    (rep / "maturity.json").write_text(json.dumps(maturity, indent=2, default=str) + "\n")

    manifest = build_manifest(
        repo_root=repo_root, contract_sha256=s0["contract_sha256"], config=cfg,
        dataset={"repo_id": cfg["dataset"]["repo_id"], "revision": s0.get("dataset_revision"),
                 "match_id": cfg["dataset"]["match_id"], "half": cfg["dataset"]["half"],
                 "video": s0.get("video_identity"), "gt_path": s0.get("gt_path")},
        windows_sha256=s0.get("windows_sha256"), detector=s1.get("detector", {}),
        reid=s1.get("reid_record", {}),
        tracker_config={**{k: tb[k] for k in ("high_score", "low_score", "iou_gate", "n_init",
                                              "max_age", "appearance_weight")},
                        "ambiguity_margin": margin, "ambiguity_terminate": tb.get("ambiguity_terminate", True)},
        offline_config=offline_cfg, seeds=cfg["seeds"], started_at=started_at, finished_at=now_iso(),
        extra={"stage0": {k: s0.get(k) for k in ("windows_sha256", "evaluator_units", "sanity_all_passed")}})
    write_manifest(rep / "artifact_manifest.json", manifest)

    ctx = {
        "maturity": maturity, "manifest": manifest,
        "stage0": {k: s0.get(k) for k in ("dataset_revision", "gt_path", "video_path", "gt_scope",
                                          "video_scope", "video_bytes", "fps", "resolution",
                                          "n_video_frames", "gt_stats", "alignment", "evaluator_units",
                                          "sanity_all_passed", "gsr_link")},
        "windows": s0["windows"], "margin_sweep": s1.get("sweep"), "selected_margin": margin,
        "px_recall_combined": s1.get("px_recall_combined", []), "recall_ge40": s1.get("recall_ge40"),
        "reid_diag": (s1.get("reid") or {}).get("pooled", {}),
        "real_rows": [row_for(r, results[r][n]) for r in FINAL for n in variants.REAL if n in results[r]],
        "oracle_rows": [row_for(r, results[r][n]) for r in FINAL for n in variants.ORACLE if n in results[r]],
        "gap_rows": gap_rows, "bottleneck": diag, "compute": s1.get("compute", {}),
        "limitations": _limitations(s0, s1, team_labels),
        "recommendation": recommendation(maturity, diag),
    }
    (rep / "executive_report.md").write_text(executive_report(ctx))
    (Path(out_root) / "state" / "stage2.json").write_text(json.dumps(
        {"maturity": maturity, "bottleneck": diag["dominant"], "finished_at": now_iso()}, indent=2) + "\n")
    return {"maturity": maturity, "bottleneck": diag}


def _diag_md(diag: dict) -> str:
    L = ["# Bottleneck diagnosis", "", "```", BANNER, "```", "",
         f"**Dominant limitation: {diag['dominant']}**", "",
         f"Evidence weight by label: `{json.dumps(diag['evidence_weight'])}`", ""]
    for clip, r in diag["per_clip"].items():
        L += [f"## {clip}: {r['label']}", "", "Fired: `" + json.dumps(r["fired"]) + "`", "",
              "Evidence:", "", "```", json.dumps(r["evidence"], indent=1), "```", ""]
    return "\n".join(L)


def _limitations(s0: dict, s1: dict, team_labels: dict) -> list[str]:
    L = [
        "Diagnostic on ONE VAL half (118578_1st), three 3-minute windows; not the frozen TEST protocol.",
        "Detector is COCO-pretrained (no football fine-tuning); ReID weights are ImageNet-derived — "
        "both RESEARCH-DIAGNOSTIC class; product models are retrained on own data.",
        "Tracker ambiguity margin tuned on TUNE only; all other parameters at repo defaults.",
        "Ignore-region handling mirrors TrackEval preprocessing but is applied by this harness.",
    ]
    if not team_labels:
        L.append("GSR role/team link unavailable: team accuracy, within-team ReID split and O4 not produced.")
    if s1.get("pass_summary", {}).get("windows"):
        inc = [r for r, v in s1["pass_summary"]["windows"].items() if v.get("status") == "INCOMPLETE"]
        if inc:
            L.append(f"Frame pass incomplete for windows {inc} — their metrics are not trustworthy.")
    if s0.get("gt_scope") == "per_match":
        L.append("Per-match GT restricted to the first-half video frame domain (alignment recorded).")
    return L
