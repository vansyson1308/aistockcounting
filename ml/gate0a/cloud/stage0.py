"""Stage 0 — real data inventory + scientific freeze (§9).

acquire(): authenticated live tree → narrow download of one match/half.
analyze(): GT audit, evaluator sanity on real v2 GT, unit convention check,
GSR role/team link (scoring only), GT-only window freeze. `analyze` is pure
local so it is testable with synthetic fixtures.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from ml.eval.mot_io import write_mot
from ml.gate0a.cloud import BANNER, hf_data, select_clips
from ml.gate0a.cloud.artifact_manifest import gpu_info, now_iso, package_versions
from ml.gate0a.cloud.contract import CONTRACT_PATH, contract_sha256
from ml.gate0a.cloud.extract_clip import check_alignment, slice_gt
from ml.gate0a.cloud.gt_policy import (
    gt_team_labels,
    link_gsr_to_mot,
    load_gsr_records,
    load_gt,
    parse_seqinfo,
    restrict_frames,
)
from ml.gate0a.cloud.secrets import describe_presence, get_secret
from ml.gate0a.runners import sanity_checks
from ml.gate0a.runners.audit_data import audit_gt

OWNER_ACTION = """OWNER UI ACTION REQUIRED:
1. Request/confirm SoccerTrack-v2 access in browser:
   https://huggingface.co/datasets/atomscott/soccertrack-v2
2. Add Kaggle secret HF_TOKEN (read token of the approved HF account).
3. Run All.
"""


class OwnerActionRequired(RuntimeError):
    pass


def report_dir(out_root: Path) -> Path:
    return Path(out_root) / "reports" / "gate0a" / "cloud" / "stage012"


def _probe_video(path: Path) -> dict:
    try:
        import cv2
    except ImportError:  # pragma: no cover
        return {"ok": False, "error": "cv2 missing"}
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return {"ok": False, "error": "cannot open"}
    info = {"ok": True, "n_frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            "fps": round(float(cap.get(cv2.CAP_PROP_FPS)), 3),
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}
    ok, _ = cap.read()
    info["first_frame_decodes"] = bool(ok)
    cap.release()
    return info


def acquire(cfg: dict, out_root: Path, scratch: Path, contract: dict) -> dict:
    """Authenticated inventory + narrow download. Raises OwnerActionRequired."""
    ds = cfg["dataset"]
    rep = report_dir(out_root)
    rep.mkdir(parents=True, exist_ok=True)
    token = get_secret("HF_TOKEN")
    presence = describe_presence()
    if not token:
        (rep / "owner_action_required.md").write_text(
            f"# {BANNER}\n\nHF_TOKEN is not available to the notebook.\n\n{OWNER_ACTION}")
        raise OwnerActionRequired("HF_TOKEN absent")
    access = hf_data.check_access(ds["repo_id"], ds["repo_type"], token)
    if access["status"] != "ok":
        (rep / "owner_action_required.md").write_text(
            f"# {BANNER}\n\nHugging Face access check: `{json.dumps(access)}`\n\n{OWNER_ACTION}")
        raise OwnerActionRequired(f"dataset access: {access['status']}")

    forbidden = list(contract["data_scope"]["forbidden_match_ids"])
    if ds["match_id"] in forbidden:
        raise PermissionError("configured match is a TEST match — refused")
    sha, entries = hf_data.resolve_tree(ds["repo_id"], ds["repo_type"], ds["revision"], token)
    inventory = hf_data.layout_inventory(entries)
    plan = hf_data.plan_download(entries, ds["match_id"], ds)
    hf_data.assert_not_forbidden(plan["files"], forbidden)
    if not plan["gt"] or not plan["video"]:
        raise RuntimeError(f"could not locate GT/video for {ds['match_id']} in live tree: {plan}")
    dry = []
    try:
        dry = hf_data.dry_run(ds["repo_id"], ds["repo_type"], sha, plan["files"], token)
    except Exception as exc:  # pragma: no cover - best effort
        dry = [{"dry_run_error": f"{type(exc).__name__}: {str(exc)[:200]}"}]
    local_dir = scratch / "hf" / ds["repo_id"].replace("/", "__")
    local_dir.mkdir(parents=True, exist_ok=True)
    small = [p for p in plan["files"] if p != plan["video"]["path"]]
    hf_data.download(ds["repo_id"], ds["repo_type"], sha, small, local_dir, token, forbidden)
    hf_data.download(ds["repo_id"], ds["repo_type"], sha, [plan["video"]["path"]], local_dir,
                     token, forbidden)
    data_inventory = {
        "banner": BANNER, "created_at": now_iso(), "secrets_present": presence,
        "dataset_revision": sha, "repo_id": ds["repo_id"], "layout": inventory,
        "selected_match_id": ds["match_id"], "selected_half": ds["half"],
        "plan": plan, "dry_run": dry, "forbidden_match_ids": forbidden,
        "note": "TEST match files are listed by the hub tree (metadata only) and never downloaded",
    }
    (rep / "data_inventory.json").write_text(json.dumps(data_inventory, indent=2, default=str) + "\n")
    return {
        "gt_path": str(local_dir / plan["gt"]["path"]),
        "gt_scope": plan["gt"]["scope"],
        "video_path": str(local_dir / plan["video"]["path"]),
        "video_scope": plan["video"]["scope"],
        "video_identity": {"path": plan["video"]["path"], "size": plan["video"]["size"],
                           "lfs_sha256": plan["video"].get("lfs_sha256"), "revision": sha},
        "seqinfo_path": str(local_dir / plan["seqinfo"]) if plan["seqinfo"] else None,
        "gsr_path": str(local_dir / plan["gsr"]) if plan["gsr"] else None,
        "dataset_revision": sha,
    }


def analyze(cfg: dict, contract: dict, out_root: Path, acq: dict) -> dict:
    """Local part of Stage 0: audit, sanity, GSR link, window freeze."""
    rep = report_dir(out_root)
    rep.mkdir(parents=True, exist_ok=True)
    data_dir = Path(out_root) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(CONTRACT_PATH, rep / "diagnostic_contract.yaml")
    csha = contract_sha256()

    gt_path = Path(acq["gt_path"])
    consider, ignore, gstats = load_gt(gt_path, drop_ignore=bool(cfg["gt"]["drop_ignore_rows"]))
    std_audit = audit_gt(gt_path)
    seqinfo = parse_seqinfo(Path(acq["seqinfo_path"]).read_text()) if acq.get("seqinfo_path") else {}
    video = _probe_video(Path(acq["video_path"]))
    if not video.get("ok"):
        raise RuntimeError(f"video not decodable: {video}")
    fps_gt = float(seqinfo.get("frameRate") or cfg["windows"]["fps_expected"])
    fps = float(video["fps"]) if video.get("fps") else fps_gt
    if abs(fps - fps_gt) > 0.05:
        raise RuntimeError(f"fps mismatch: video {fps} vs GT {fps_gt} — fail closed")
    align = check_alignment(max(consider), video["n_frames"], fps_gt, video.get("fps"))
    n_video = int(video["n_frames"])
    consider_v = restrict_frames(consider, n_video)
    ignore_v = restrict_frames(ignore, n_video)
    gt_consider_path = data_dir / "gt_consider.txt"
    rows = [(f, tid, b[0], b[1], b[2] - b[0], b[3] - b[1], 1.0)
            for f in sorted(consider_v) for tid, b, _c in consider_v[f]]
    write_mot(gt_consider_path, rows)
    ign_rows = [(f, tid, b[0], b[1], b[2] - b[0], b[3] - b[1], 0.0)
                for f in sorted(ignore_v) for tid, b, _c in ignore_v[f]]
    write_mot(data_dir / "gt_ignore.txt", ign_rows)

    # Evaluator sanity on REAL v2 GT (bounded slice for runtime), unit convention.
    max_f = int(cfg.get("sanity_max_frames", 15000))
    first = min(consider_v)
    slice_rows = [r for r in rows if r[0] < first + max_f]
    sanity_path = data_dir / "gt_sanity_slice.txt"
    write_mot(sanity_path, slice_rows)
    sanity = sanity_checks.run(sanity_path, None, drop_fraction=0.3)
    a = sanity["A_perfect_prediction"]
    units = "fraction" if all(0.0 <= float(a[k]) <= 1.0 for k in ("hota", "deta", "assa", "idf1")) else "percent"
    sanity["evaluator_units"] = {"canonical": units, "contract_expects": contract["metric_units"]["canonical"],
                                 "slice_frames": max_f}
    (rep / "evaluator_sanity.json").write_text(json.dumps(sanity, indent=2, default=str) + "\n")
    if units != contract["metric_units"]["canonical"]:
        raise RuntimeError("evaluator unit convention differs from the contract — fail closed")
    if not sanity["all_passed"]:
        raise RuntimeError("evaluator sanity FAILED on real v2 GT — fail closed")

    # GSR role/team link (SCORING ONLY).
    gsr_summary: dict = {"available": False}
    team_labels: dict[int, str] = {}
    if acq.get("gsr_path") and Path(acq["gsr_path"]).exists():
        try:
            recs = load_gsr_records(Path(acq["gsr_path"]))
            link = link_gsr_to_mot(consider_v, recs)
            team_labels = gt_team_labels(link)
            roles: dict[str, int] = {}
            teams: dict[str, int] = {}
            for v in link.values():
                roles[str(v["role"])] = roles.get(str(v["role"]), 0) + 1
                teams[str(v["team"])] = teams.get(str(v["team"]), 0) + 1
            gsr_summary = {"available": True, "records": len(recs), "linked_ids": len(link),
                           "gt_ids": gstats["ids"], "roles": roles, "teams": teams,
                           "team_labeled_ids": len(team_labels)}
            (data_dir / "gt_team_labels.json").write_text(json.dumps(team_labels, indent=1) + "\n")
        except Exception as exc:
            gsr_summary = {"available": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}

    # Frozen diagnostic windows (GT only) — never regenerated once predictions exist.
    win_path = rep / "diagnostic_windows.yaml"
    cache_root = Path(out_root) / "cache"
    preds_exist = any((cache_root / r / "det.txt").exists() for r in select_clips.ROLES)
    if win_path.exists():
        windows_doc, wsha = select_clips.load_frozen(win_path)
        windows = windows_doc["windows"]
    else:
        if preds_exist:
            raise RuntimeError("predictions exist but no frozen windows file — refusing to select now")
        windows = select_clips.select_windows(consider_v, fps, cfg["windows"], frame_max=n_video)
        wsha = select_clips.freeze(windows, {
            "source_half": f"{cfg['dataset']['match_id']}_{cfg['dataset']['half']}",
            "gt_path": acq["gt_path"], "dataset_revision": acq.get("dataset_revision"),
            "fps": fps, "frozen_at": now_iso(), "diagnostic_contract_sha256": csha,
            "params": cfg["windows"],
        }, win_path)
    shutil.copy(win_path, data_dir / "diagnostic_windows.yaml")
    for role, w in windows.items():
        gt_w = slice_gt(consider_v, w["start_frame"], w["end_frame"])
        w_rows = [(f, tid, b[0], b[1], b[2] - b[0], b[3] - b[1], 1.0)
                  for f in sorted(gt_w) for tid, b, _c in gt_w[f]]
        write_mot(data_dir / f"gt_{role}.txt", w_rows)

    integrity = {
        "banner": BANNER, "gt_path": acq["gt_path"], "gt_scope": acq.get("gt_scope"),
        "video_path": acq["video_path"], "video_scope": acq.get("video_scope"),
        "video": video, "seqinfo": seqinfo, "fps": fps, "gt_policy_stats": gstats,
        "standard_audit": std_audit, "alignment": align,
        "gt_frames_in_video_domain": len(consider_v), "gsr_link": gsr_summary,
    }
    (rep / "data_integrity.json").write_text(json.dumps(integrity, indent=2, default=str) + "\n")
    md = ["# Gate 0A cloud Stage 0 — data integrity", "", "```", BANNER, "```", "",
          f"- GT: `{acq['gt_path']}` ({acq.get('gt_scope')}), sha256 `{std_audit['sha256'][:16]}…`",
          f"- rows {gstats['rows']}, ignore rows {gstats['ignore_rows']}, invalid {gstats['invalid_rows']}, "
          f"ids {gstats['ids']}, frames {gstats['frames']} in {gstats['frame_range']}",
          f"- class histogram {gstats['class_histogram']}, visibility mean {gstats['visibility_mean']}",
          f"- bbox height px {gstats['bbox_height_px']}; boxes/frame {gstats['boxes_per_frame']}",
          f"- video: `{acq['video_path']}` ({acq.get('video_scope')}) {video['width']}x{video['height']} "
          f"@ {video['fps']} fps, {video['n_frames']} frames ({video['n_frames'] / fps / 60:.1f} min)",
          f"- seqinfo: {seqinfo}", f"- alignment: {align}",
          f"- GSR link: {gsr_summary}", f"- evaluator units: {units}; sanity all passed: {sanity['all_passed']}",
          f"- frozen windows sha256: `{wsha}`", ""]
    (rep / "data_integrity.md").write_text("\n".join(md))
    (rep / "environment.json").write_text(json.dumps({
        "banner": BANNER, "created_at": now_iso(), **gpu_info(),
        "packages": package_versions(("torch", "torchvision", "transformers", "huggingface_hub",
                                      "opencv-python-headless", "numpy", "trackeval")),
        "disk": {p: shutil.disk_usage(p)._asdict() for p in (str(out_root),) if Path(p).exists()},
    }, indent=2, default=str) + "\n")

    state = {
        **acq, "fps": fps, "n_video_frames": n_video, "resolution": [video["width"], video["height"]],
        "gt_consider_path": str(gt_consider_path), "gt_ignore_path": str(data_dir / "gt_ignore.txt"),
        "gt_team_labels_path": str(data_dir / "gt_team_labels.json") if team_labels else None,
        "windows_path": str(win_path), "windows_sha256": wsha, "windows": windows,
        "contract_sha256": csha, "evaluator_units": units, "sanity_all_passed": sanity["all_passed"],
        "gt_stats": gstats, "alignment": align, "gsr_link": gsr_summary,
        "video_bytes": acq.get("video_identity", {}).get("size"),
    }
    state_dir = Path(out_root) / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "stage0.json").write_text(json.dumps(state, indent=2, default=str) + "\n")
    return state
