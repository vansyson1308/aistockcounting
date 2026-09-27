#!/usr/bin/env python3
"""Compose the final 1080p demo video from frames, clips and narration (ffmpeg).

Inputs (produced by build.sh): ``build/frames/*.png`` (slides.py), ``clips/*.webm``
(record.py), ``build/audio/*.wav`` + ``durations.json`` (narrate.py) and, if
present, ``raw/team_intro.mp4``. Output: ``trayagent_demo.mp4`` (H.264 1920x1080
30 fps, AAC 48 kHz, no music) and ``trayagent_demo.srt`` (English). The SRT is
also muxed into the MP4 as a soft subtitle track.

Each segment lasts max(narration + 0.8 s, its visual). A recording shorter than
its narration holds its last frame. The script fails if the total exceeds 300 s.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
FPS = 30
MAX_TOTAL = 300.0
SLIDE_MIN = 5.0
INTRO_CARD = 5.0
PHONE_H = 1000
PHONE_X_CENTER = 46 + 628 // 2  # centre of the frame drawn by slides.py
PHONE_Y = 40


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        text=True,
    ).strip()
    return float(out)


VENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS)]
AENC = ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]


def audio_input(wav: Path | None, dur: float) -> list[str]:
    if wav is not None and wav.exists():
        return ["-i", str(wav)]
    return ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]


def seg_slide(png: Path, wav: Path | None, dur: float, out: Path) -> None:
    run(
        ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", str(png)]
        + audio_input(wav, dur)
        + ["-filter_complex", f"[1:a]apad,atrim=0:{dur:.3f}[a]", "-map", "0:v", "-map", "[a]", "-t", f"{dur:.3f}"]
        + VENC + AENC + [str(out)]
    )


def seg_recording(bg: Path, clip: Path, wav: Path | None, dur: float, out: Path) -> None:
    clip_d = probe_duration(clip)
    hold = max(0.0, dur - clip_d)
    vf = (
        f"[1:v]scale=-2:{PHONE_H}:flags=lanczos,setsar=1,fps={FPS},"
        f"tpad=stop_mode=clone:stop_duration={hold:.3f}[ph];"
        f"[0:v][ph]overlay=x={PHONE_X_CENTER}-w/2:y={PHONE_Y}:shortest=1,format=yuv420p[v];"
        f"[2:a]apad,atrim=0:{dur:.3f}[a]"
    )
    run(
        ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", str(bg), "-i", str(clip)]
        + audio_input(wav, dur)
        + ["-filter_complex", vf, "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}"]
        + VENC + AENC + [str(out)]
    )


def seg_intro_clip(clip: Path, max_s: float, out: Path) -> float:
    dur = min(max_s, probe_duration(clip))
    has_audio = bool(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(clip)],
            text=True,
        ).strip()
    )
    vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(clip)]
    if not has_audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v", "-map", "1:a"]
    cmd += ["-vf", vf, "-t", f"{dur:.3f}"] + VENC + AENC + [str(out)]
    run(cmd)
    return dur


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt_cues(text: str, start: float, speech: float) -> list[tuple[float, float, str]]:
    """Split narration into sentence cues, timed in proportion to their length."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?:])\s+", text.strip()) if p.strip()]
    chunks: list[str] = []
    for p in parts:  # keep cues short enough to read (about 90 characters)
        words, cur = p.split(), ""
        for w in words:
            if len(cur) + len(w) + 1 > 90 and cur:
                chunks.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}".strip()
        if cur:
            chunks.append(cur)
    total = sum(len(c) for c in chunks) or 1
    t, cues = start, []
    for c in chunks:
        d = speech * len(c) / total
        cues.append((t, t + d, c))
        t += d
    return cues


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--segments", default=str(HERE / "segments.yaml"))
    ap.add_argument("--build", default=str(HERE / "build"))
    ap.add_argument("--clips", default=str(HERE / "clips"))
    ap.add_argument("--out", default=str(HERE / "trayagent_demo.mp4"))
    args = ap.parse_args()

    build = Path(args.build)
    frames, audio, parts_dir = build / "frames", build / "audio", build / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    durs = json.loads((audio / "durations.json").read_text())["durations"]
    segs = yaml.safe_load(Path(args.segments).read_text())["segments"]

    parts, timeline, cues, t = [], [], [], 0.0
    for seg in segs:
        sid = seg["id"]
        wav = audio / f"{sid}.wav" if sid in durs else None
        speech = durs.get(sid, 0.0)
        out = parts_dir / f"{len(parts):02d}_{sid}.mp4"
        if seg["kind"] == "intro":
            clip = HERE / seg["source"]
            if clip.exists():
                dur = seg_intro_clip(clip, float(seg.get("max_seconds", 30)), out)
                src = str(clip)
            else:
                dur = INTRO_CARD
                seg_slide(frames / f"{sid}.png", None, dur, out)
                src = "title card (team_intro.mp4 missing)"
        elif seg["kind"] == "slide":
            dur = max(SLIDE_MIN, speech + 0.8)
            seg_slide(frames / f"{sid}.png", wav, dur, out)
            src = "slide"
        else:
            clip = Path(args.clips) / Path(seg["source"]).name
            if not clip.exists():
                raise SystemExit(f"missing recording {clip}; run record.py first")
            dur = max(speech + 0.8, probe_duration(clip))
            seg_recording(frames / f"{sid}.png", clip, wav, dur, out)
            src = str(clip)
        if speech:
            cues += srt_cues(seg["narration"], t + 0.2, speech)
        timeline.append({"id": sid, "start": round(t, 2), "duration": round(dur, 2), "source": src})
        parts.append(out)
        t += dur

    if t > MAX_TOTAL:
        raise SystemExit(f"video would be {t:.1f}s (> {MAX_TOTAL:.0f}s); shorten the narration or clips")

    listing = parts_dir / "concat.txt"
    listing.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    srt = Path(args.out).with_suffix(".srt")
    srt.write_text(
        "".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{txt}\n\n" for i, (a, b, txt) in enumerate(cues, 1))
    )
    joined = parts_dir / "joined.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(joined)])
    run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(joined), "-i", str(srt), "-map", "0", "-map", "1",
         "-c", "copy", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng", "-movflags", "+faststart", args.out]
    )
    (build / "timeline.json").write_text(json.dumps({"total_seconds": round(t, 2), "segments": timeline}, indent=2))
    print(json.dumps({"total_seconds": round(t, 2), "out": args.out, "srt": str(srt)}))


if __name__ == "__main__":
    main()
