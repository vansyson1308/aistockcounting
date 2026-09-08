"""Clip slicing utilities: GT window slicing with frame renumbering, video ↔ GT
alignment checks, and best-effort ffmpeg export of the frozen windows.

Inference itself never depends on exported clips: `frame_pass` decodes the
source video sequentially with an exact frame counter. Exports exist only so
the persisted outputs remain inspectable without the multi-GB source.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def slice_gt(frames: dict, start: int, end: int, renumber: bool = True) -> dict:
    """Frames in [start, end] (inclusive, 1-based); renumbered to start at 1."""
    out = {}
    for f in range(start, end + 1):
        dets = frames.get(f)
        if dets:
            out[f - start + 1 if renumber else f] = list(dets)
    return out


def slice_keyed(d: dict, start: int, end: int, renumber: bool = True) -> dict:
    """Same as slice_gt for {(frame, idx): value} dicts."""
    out = {}
    for (f, i), v in d.items():
        if start <= f <= end:
            out[(f - start + 1 if renumber else f, i)] = v
    return out


def check_alignment(gt_max_frame: int, n_video_frames: int | None, fps_gt: float | None,
                    fps_video: float | None, tolerance_frames: int = 2) -> dict:
    res = {"gt_max_frame": gt_max_frame, "n_video_frames": n_video_frames,
           "fps_gt": fps_gt, "fps_video": fps_video, "ok": True, "notes": []}
    if n_video_frames is None:
        res["ok"] = False
        res["notes"].append("video frame count unavailable")
        return res
    if gt_max_frame > n_video_frames + tolerance_frames:
        res["notes"].append(
            "GT extends beyond the decoded video (per-match GT vs half video?) — "
            "GT restricted to the video frame domain")
    if fps_gt and fps_video and abs(fps_gt - fps_video) > 0.05:
        res["ok"] = False
        res["notes"].append(f"fps mismatch GT {fps_gt} vs video {fps_video}")
    return res


def ffmpeg_extract_cmd(video: Path, start_frame: int, end_frame: int, out: Path) -> list[str]:
    """Exact frame-index selection (0-based n) — no timestamp rounding."""
    n0, n1 = start_frame - 1, end_frame - 1
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
        "-vf", f"select='between(n,{n0},{n1})',setpts=N/FRAME_RATE/TB",
        "-vsync", "vfr", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        str(out),
    ]


def count_frames(video: Path) -> int | None:
    try:
        import cv2
    except ImportError:  # pragma: no cover
        return None
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return None
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return n if n > 0 else None


def export_clip(video: Path, start_frame: int, end_frame: int, out: Path) -> dict:
    if shutil.which("ffmpeg") is None:
        return {"ok": False, "reason": "ffmpeg not available"}
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ffmpeg_extract_cmd(video, start_frame, end_frame, out)
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=3600)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "reason": str(exc)[:300]}
    n = count_frames(out)
    expected = end_frame - start_frame + 1
    return {"ok": n == expected, "path": str(out), "n_frames": n, "expected": expected}
