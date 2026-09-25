#!/usr/bin/env python3
"""Text-to-speech narration for each segment of segments.yaml.

    python demo/video/narrate.py --tts polly --voice Matthew     # Amazon Polly (neural)
    python demo/video/narrate.py --tts espeak                    # offline placeholder

Writes ``build/audio/<segment>.wav`` (48 kHz mono) and ``build/audio/durations.json``.
Polly uses ``synthesize_speech(Engine="neural", OutputFormat="pcm", SampleRate="16000")``;
the API shape was checked against the botocore service model. espeak-ng is a
robotic offline fallback that lets the pipeline be tested without AWS
credentials. Use Polly for the real video.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import wave
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def polly_wav(text: str, out: Path, voice: str, region: str) -> None:
    import boto3

    client = boto3.client("polly", region_name=region)
    resp = client.synthesize_speech(
        Engine="neural", OutputFormat="pcm", SampleRate="16000", Text=text, VoiceId=voice
    )
    raw = out.with_suffix(".pcm.wav")
    with wave.open(str(raw), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(resp["AudioStream"].read())
    _resample(raw, out)
    raw.unlink()


def espeak_wav(text: str, out: Path) -> None:
    raw = out.with_suffix(".raw.wav")
    subprocess.run(["espeak-ng", "-v", "en-us", "-s", "158", "-w", str(raw), text], check=True)
    _resample(raw, out)
    raw.unlink()


def _resample(src: Path, dst: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ar", "48000", "-ac", "1", str(dst)],
        check=True,
    )


def duration(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / float(w.getframerate())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--segments", default=str(HERE / "segments.yaml"))
    ap.add_argument("--out", default=str(HERE / "build" / "audio"))
    ap.add_argument("--tts", choices=["polly", "espeak"], default="polly")
    ap.add_argument("--voice", default="Matthew")
    ap.add_argument("--region", default="us-east-1")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    durations: dict[str, float] = {}
    for seg in yaml.safe_load(Path(args.segments).read_text())["segments"]:
        text = (seg.get("narration") or "").strip()
        if not text:
            continue
        wav = out / f"{seg['id']}.wav"
        if args.tts == "polly":
            polly_wav(text, wav, args.voice, args.region)
        else:
            espeak_wav(text, wav)
        durations[seg["id"]] = round(duration(wav), 3)
        print(f"{seg['id']}: {durations[seg['id']]:.1f}s")
    (out / "durations.json").write_text(json.dumps({"tts": args.tts, "durations": durations}, indent=2))


if __name__ == "__main__":
    main()
