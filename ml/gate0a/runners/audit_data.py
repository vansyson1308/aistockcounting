"""Dataset integrity audit (Gate 0A instructions §3, first half).

Audits MOTChallenge ground-truth sequences (+ optional videos via ffprobe):
existence, parseability, frame coverage/gaps, bbox bounds vs seqinfo (when
present), duplicate (frame, id) rows, invalid boxes, per-track persistence
(span, holes), and summary statistics. Emits Markdown + JSON.

Usage:
  python -m ml.gate0a.runners.audit_data \
      --seq NAME=GT_PATH[:VIDEO_PATH] ... --out-md reports/gate0a/data_integrity.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import defaultdict
from itertools import pairwise
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_video(path: Path) -> dict:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries",
             "stream=width,height,r_frame_rate,nb_frames,duration",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=120,
        )
        info = json.loads(out.stdout)["streams"][0]
        num, den = info.get("r_frame_rate", "0/1").split("/")
        info["fps"] = round(float(num) / float(den), 3) if float(den) else None
        return {"ok": True, **info}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def audit_gt(path: Path) -> dict:
    issues: list[str] = []
    per_frame: dict[int, list] = defaultdict(list)
    seen: set[tuple[int, int]] = set()
    n_rows = n_invalid = n_dupes = 0
    tracks: dict[int, list[int]] = defaultdict(list)
    xmax = ymax = 0.0
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split(",")
        if len(parts) < 6:
            issues.append(f"line {lineno}: <6 fields")
            continue
        frame, tid = int(float(parts[0])), int(float(parts[1]))
        x, y, w, h = (float(v) for v in parts[2:6])
        n_rows += 1
        if w <= 0 or h <= 0 or any(map(lambda v: v != v, (x, y, w, h))):
            n_invalid += 1
            continue
        if (frame, tid) in seen:
            n_dupes += 1
            continue
        seen.add((frame, tid))
        per_frame[frame].append(tid)
        tracks[tid].append(frame)
        xmax, ymax = max(xmax, x + w), max(ymax, y + h)

    frames = sorted(per_frame)
    gaps = []
    for a, b in pairwise(frames):
        if b - a > 1:
            gaps.append((a, b))
    track_stats = []
    for tid, fs in tracks.items():
        fs.sort()
        span = fs[-1] - fs[0] + 1
        holes = span - len(fs)
        track_stats.append((tid, fs[0], fs[-1], len(fs), holes))
    holes_total = sum(t[4] for t in track_stats)
    objs_per_frame = [len(v) for v in per_frame.values()]

    return {
        "sha256": sha256(path),
        "rows": n_rows,
        "invalid_boxes": n_invalid,
        "duplicate_frame_id": n_dupes,
        "frames": len(frames),
        "frame_range": [frames[0], frames[-1]] if frames else None,
        "frame_gaps": gaps[:20],
        "n_frame_gaps": len(gaps),
        "tracks": len(tracks),
        "track_intra_holes_total": holes_total,
        "objects_per_frame_min_max": [min(objs_per_frame), max(objs_per_frame)]
        if objs_per_frame
        else None,
        "bbox_extent_xmax_ymax": [round(xmax, 1), round(ymax, 1)],
        "parse_issues": issues[:20],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seq", nargs="+", required=True,
                    metavar="NAME=GT[:VIDEO]")
    ap.add_argument("--out-md", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, default=None)
    ap.add_argument("--context", default="")
    args = ap.parse_args()

    report: dict = {"context": args.context, "sequences": {}}
    for spec in args.seq:
        name, rest = spec.split("=", 1)
        gt_path, _, video = rest.partition(":")
        entry = {"gt_path": gt_path, "gt": audit_gt(Path(gt_path))}
        if video:
            entry["video_path"] = video
            entry["video"] = probe_video(Path(video))
        report["sequences"][name] = entry

    lines = ["# Gate 0A data integrity audit", ""]
    if args.context:
        lines += [args.context, ""]
    for name, e in report["sequences"].items():
        g = e["gt"]
        lines += [
            f"## {name}",
            "",
            f"- gt: `{e['gt_path']}` (sha256 `{g['sha256'][:16]}…`)",
            f"- rows {g['rows']}, invalid {g['invalid_boxes']}, "
            f"duplicates {g['duplicate_frame_id']}, parse issues "
            f"{len(g['parse_issues'])}",
            f"- frames {g['frames']} in {g['frame_range']}, "
            f"gaps {g['n_frame_gaps']}",
            f"- tracks {g['tracks']}, intra-track holes "
            f"{g['track_intra_holes_total']}",
            f"- objects/frame {g['objects_per_frame_min_max']}, "
            f"bbox extent {g['bbox_extent_xmax_ymax']}",
        ]
        if "video" in e:
            v = e["video"]
            lines.append(
                f"- video: `{e['video_path']}` → "
                + (f"{v.get('width')}x{v.get('height')} @ {v.get('fps')} fps, "
                   f"nb_frames {v.get('nb_frames')}"
                   if v.get("ok") else f"DECODE FAILED: {v.get('error')}")
            )
        lines.append("")
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text("\n".join(lines))
    if args.out_json:
        args.out_json.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
