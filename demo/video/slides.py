#!/usr/bin/env python3
"""Render the video's still frames (1920x1080 PNG) from segments.yaml.

* ``intro``: a title card (used only when raw/team_intro.mp4 is missing).
* ``slide``: a title and bullets, plus an optional image, or the results table
  read from ``reports/agentic/summary.json``. When that file is missing, the
  slide says so plainly and shows no numbers.
* ``recording``: a background panel with the title and bullets on the right.
  build.sh overlays the phone recording on the left half.

A ``--watermark`` text (e.g. "PIPELINE TEST: SYNTHETIC TRAYS") is stamped on
every frame.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
BG = (15, 23, 42)
FG = (241, 245, 249)
MUTED = (148, 163, 184)
ACCENT = (129, 140, 248)
WARN = (251, 191, 36)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
HERE = Path(__file__).resolve().parent


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(FONT_B if bold else FONT, size)
    except OSError:
        return ImageFont.load_default()


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if draw.textlength(t, font=fnt) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def base(watermark: str | None) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - 8, W, H], fill=ACCENT)
    foot = "TrayAgent · OpenCV AI Competition 2026"
    d.text((W - 60 - d.textlength(foot, font=font(24)), H - 50), foot, font=font(24), fill=MUTED)
    if watermark:
        f = font(30, True)
        tw = d.textlength(watermark, font=f)
        d.rectangle([W - tw - 80, 20, W - 20, 70], fill=(120, 53, 15))
        d.text((W - tw - 50, 27), watermark, font=f, fill=WARN)
    return img, d


def bullets(d, items, x, y, width, size=38) -> int:
    f = font(size)
    for b in items:
        lines = wrap(d, b, f, width - 50)
        d.ellipse([x, y + size // 2 - 7, x + 14, y + size // 2 + 7], fill=ACCENT)
        for ln in lines:
            d.text((x + 40, y), ln, font=f, fill=FG)
            y += int(size * 1.35)
        y += int(size * 0.5)
    return y


def results_lines(path: Path) -> list[str] | None:
    if not path.exists():
        return None
    s = json.loads(path.read_text())
    if not s.get("reportable"):
        return None
    a = s["agentic"]["pos_correct"]

    def pct(x):
        return "n/a" if x is None or x != x else f"{100 * x:.1f}%"

    def num(x):
        return "n/a" if x is None or x != x else f"{x:.2f}"

    return [
        f"{s['test_images']} real test photos, {s['test_items']} items (frozen split)",
        f"mAP@0.5 {num(s['map50_single_shot'])}",
        f"Exact count: single shot {pct(s['single_shot']['exact'])} → TrayAgent {pct(a['count']['exact'])}",
        f"Count MAE: {num(s['single_shot']['mae'])} → {num(a['count']['mae'])}",
        f"Escalated {pct(a['escalation_rate'])} · re-shot {pct(a['recapture_rate'])} · false auto-accept {pct(a['false_auto_accept_rate'])}",
        f"Latency p50/p95 on {s['machine']}: {a['latency_ms_p50']:.0f} / {a['latency_ms_p95']:.0f} ms",
    ]


def render(seg: dict, out: Path, watermark: str | None) -> Path:
    img, d = base(watermark)
    kind = seg["kind"]
    if kind == "intro":
        d.text((120, 380), seg.get("title", ""), font=font(120, True), fill=FG)
        for i, ln in enumerate(wrap(d, seg.get("subtitle", ""), font(46), W - 240)):
            d.text((120, 540 + i * 62), ln, font=font(46), fill=MUTED)
        d.text((120, 760), "Team intro clip goes here (demo/video/raw/team_intro.mp4)", font=font(30), fill=WARN)
    elif kind == "slide":
        d.text((100, 80), seg["title"], font=font(72, True), fill=FG)
        y = 220
        if seg.get("results_from"):
            lines = results_lines((HERE / seg["results_from"]).resolve())
            if lines is None:
                d.text((100, y), "Results pending: real photos not yet labelled.", font=font(46, True), fill=WARN)
                d.text((100, y + 80), "No accuracy numbers are shown until the frozen real test set exists.", font=font(36), fill=MUTED)
            else:
                bullets(d, lines, 100, y, W - 200, 40)
        elif seg.get("image") and (HERE / seg["image"]).exists():
            pic = Image.open(HERE / seg["image"]).convert("RGB")
            pic.thumbnail((1100, 780))
            img.paste(pic, (80, 200))
            bullets(d, seg.get("bullets", []), 1240, 240, 620, 32)
        else:
            bullets(d, seg.get("bullets", []), 100, y, W - 200, 44)
    else:  # recording: text panel on the right, the phone video goes on the left
        d.rounded_rectangle([46, 26, 46 + 628, 26 + 1028], radius=28, outline=(51, 65, 85), width=4)
        y = 140
        for ln in wrap(d, seg["title"], font(56, True), W - 780):
            d.text((720, y), ln, font=font(56, True), fill=FG)
            y += 72
        bullets(d, seg.get("bullets", []), 720, y + 70, W - 780, 38)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", default=str(HERE / "segments.yaml"))
    ap.add_argument("--out", default=str(HERE / "build" / "frames"))
    ap.add_argument("--watermark", default=None)
    args = ap.parse_args()
    segs = yaml.safe_load(Path(args.segments).read_text())["segments"]
    for seg in segs:
        p = render(seg, Path(args.out) / f"{seg['id']}.png", args.watermark)
        print(p)


if __name__ == "__main__":
    main()
