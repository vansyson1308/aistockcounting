"""Single sequential pass over the source video (crown-jewel cache, §10).

For every frame inside a frozen window the pass produces, once:
  * real detector boxes            → <ROLE>/det.txt   (MOT det rows, window-local frames)
  * real embeddings of those boxes → <ROLE>/det_emb.npz
  * real embeddings of GT boxes    → <ROLE>/gt_emb.npz  (Oracle O2/O3 only)
plus timing. Everything downstream (MOT, reconciliation, TrackEval) is CPU
and re-runnable from these files without touching the GPU or the video.

Frames are counted with an exact decode counter (no timestamp seeking).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from ml.eval.mot_io import write_mot
from ml.gate0a.cloud import CLOUD_LAYER_VERSION, cache
from ml.gate0a.cloud.detector_adapter import to_mot_det_rows

REQUIRED_FILES = ("det.txt", "det_emb.npz", "gt_emb.npz", "pass.json")


def window_spec(video_identity: dict, window: dict, detector_desc: dict, reid_desc: dict) -> dict:
    keep_det = {k: detector_desc.get(k) for k in (
        "hf_id", "revision", "weights_sha256", "tile_px", "overlap_px", "nms_iou",
        "model_input_px", "precision")}
    keep_reid = {k: reid_desc.get(k) for k in ("arch", "weights", "weights_sha256", "crop_hw")}
    return {"version": CLOUD_LAYER_VERSION, "video": video_identity,
            "window": {k: window[k] for k in ("start_frame", "end_frame")},
            "detector": keep_det, "reid": keep_reid}


def _save_emb(path: Path, keys: list[tuple[int, int]], vecs: list[np.ndarray], dtype) -> None:
    if keys:
        frames = np.array([k[0] for k in keys], dtype=np.int32)
        idx = np.array([k[1] for k in keys], dtype=np.int32)
        emb = np.stack(vecs).astype(dtype)
    else:
        frames, idx, emb = np.zeros(0, np.int32), np.zeros(0, np.int32), np.zeros((0, 0), dtype)
    np.savez(path, frames=frames, idx=idx, emb=emb)


def load_emb(path: Path) -> dict[tuple[int, int], np.ndarray]:
    z = np.load(path)
    emb = z["emb"].astype(np.float32)
    return {(int(f), int(i)): emb[k] for k, (f, i) in enumerate(zip(z["frames"], z["idx"], strict=True))}


def run_frame_pass(
    video: Path, windows: dict[str, dict], gt_consider: dict, detector, embedder,
    out_root: Path, video_identity: dict, store_dtype=np.float16,
) -> dict:
    """Decode once; process only frames inside windows; write per-window caches."""
    import cv2

    det_desc = detector.describe()
    reid_desc = embedder.describe()
    plan = []
    for role, w in sorted(windows.items(), key=lambda kv: kv[1]["start_frame"]):
        wdir = out_root / role
        spec = window_spec(video_identity, w, det_desc, reid_desc)
        status, _h = cache.check(wdir, "frame_pass", spec, [wdir / f for f in REQUIRED_FILES])
        plan.append({"role": role, "window": w, "dir": wdir, "spec": spec, "status": status})
        print(f"[frame_pass] {role} frames {w['start_frame']}-{w['end_frame']}: {status}")
    todo = [p for p in plan if p["status"] == cache.RECOMPUTE]
    summary = {"windows": {p["role"]: {"status": p["status"]} for p in plan}}
    if not todo:
        return summary

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video {video}")
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except Exception:  # pragma: no cover
        torch = None

    last_end = max(p["window"]["end_frame"] for p in todo)
    buffers = {p["role"]: {"rows": [], "dk": [], "dv": [], "gk": [], "gv": [],
                           "frames_seen": 0, "t0": time.perf_counter(), "n_dets": 0}
               for p in todo}
    frame = 0
    while frame < last_end:
        ok = cap.grab()
        if not ok:
            break
        frame += 1
        active = [p for p in todo if p["window"]["start_frame"] <= frame <= p["window"]["end_frame"]]
        if not active:
            continue
        ok, bgr = cap.retrieve()
        if not ok:
            break
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        for p in active:
            role, w, buf = p["role"], p["window"], buffers[p["role"]]
            local = frame - w["start_frame"] + 1
            boxes, scores = detector.detect_frame(rgb, window=role)
            buf["rows"].extend(to_mot_det_rows(local, boxes, scores))
            buf["n_dets"] += len(boxes)
            if len(boxes):
                keep, vecs = embedder.embed(rgb, boxes)
                for i, v in zip(keep, vecs, strict=True):
                    buf["dk"].append((local, int(i)))
                    buf["dv"].append(v)
            gts = gt_consider.get(frame, [])
            if gts:
                keep, vecs = embedder.embed(rgb, [b for _, b, _ in gts])
                for i, v in zip(keep, vecs, strict=True):
                    buf["gk"].append((local, int(i)))
                    buf["gv"].append(v)
            buf["frames_seen"] += 1
    cap.release()

    peak = None
    if torch is not None and torch.cuda.is_available():
        peak = round(torch.cuda.max_memory_allocated() / 2**30, 3)
    for p in todo:
        role, w, wdir, buf = p["role"], p["window"], p["dir"], buffers[p["role"]]
        expected = w["end_frame"] - w["start_frame"] + 1
        complete = buf["frames_seen"] == expected
        wdir.mkdir(parents=True, exist_ok=True)
        write_mot(wdir / "det.txt", buf["rows"])
        _save_emb(wdir / "det_emb.npz", buf["dk"], buf["dv"], store_dtype)
        _save_emb(wdir / "gt_emb.npz", buf["gk"], buf["gv"], store_dtype)
        rec = {"role": role, "window": w, "frames_seen": buf["frames_seen"], "expected": expected,
               "complete": complete, "n_detections": buf["n_dets"],
               "n_det_embeddings": len(buf["dk"]), "n_gt_embeddings": len(buf["gk"]),
               "wall_seconds": round(time.perf_counter() - buf["t0"], 2), "peak_vram_gb": peak}
        (wdir / "pass.json").write_text(json.dumps(rec, indent=2) + "\n")
        if complete:
            cache.commit(wdir, "frame_pass", p["spec"], [wdir / f for f in REQUIRED_FILES])
        summary["windows"][role] = {"status": "COMPUTED" if complete else "INCOMPLETE", **rec}
    summary["detector_profile"] = detector.profile.finish()
    summary["detector_profile"]["peak_vram_gb"] = peak
    summary["embed_profile"] = embedder.profile.finish()
    return summary
