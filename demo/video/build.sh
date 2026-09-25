#!/usr/bin/env bash
# Build the TrayAgent demo video end to end.
#
#   demo/video/build.sh                          # slides + narration (Polly) + compose; uses existing clips/
#   RECORD=1 BASE_URL=https://dxxx.cloudfront.net demo/video/build.sh   # also re-record the clips
#   TTS=espeak demo/video/build.sh               # offline placeholder narration
#   WATERMARK="PIPELINE TEST" DEMO_DIR=/tmp/synth demo/video/build.sh   # rehearsal
#
# Output: demo/video/trayagent_demo.mp4 (1080p, <= 5:00, no music) and trayagent_demo.srt.
# The team intro is demo/video/raw/team_intro.mp4 (a title card is used if missing).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
TTS="${TTS:-polly}"
OUT="${OUT:-$HERE/trayagent_demo.mp4}"
CLIPS="${CLIPS:-$HERE/clips}"
BUILD="${BUILD:-$HERE/build}"

for tool in ffmpeg ffprobe; do command -v "$tool" >/dev/null || { echo "missing $tool" >&2; exit 2; }; done

echo "[1/4] slides"
wm=()
[[ -n "${WATERMARK:-}" ]] && wm=(--watermark "$WATERMARK")
"$PY" "$HERE/slides.py" --out "$BUILD/frames" "${wm[@]}" >/dev/null

if [[ "${RECORD:-0}" == "1" ]]; then
  echo "[2/4] recording scenarios A/B/C against ${BASE_URL:?set BASE_URL}"
  demo=()
  [[ -n "${DEMO_DIR:-}" ]] && demo=(--demo-dir "$DEMO_DIR")
  "$PY" "$HERE/record.py" --base-url "$BASE_URL" --out "$CLIPS" "${demo[@]}"
  cat "$CLIPS/record_log.json"
else
  echo "[2/4] recording skipped (RECORD=1 to re-record); using $CLIPS"
fi

echo "[3/4] narration ($TTS)"
"$PY" "$HERE/narrate.py" --tts "$TTS" --out "$BUILD/audio" ${POLLY_VOICE:+--voice "$POLLY_VOICE"} ${AWS_REGION:+--region "$AWS_REGION"}

echo "[4/4] compose"
"$PY" "$HERE/compose.py" --build "$BUILD" --clips "$CLIPS" --out "$OUT"

dur="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT")"
size="$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "$OUT")"
echo "video: $OUT  duration=${dur}s  size=${size}"
awk -v d="$dur" 'BEGIN { exit !(d <= 300.0) }' || { echo "FAIL: longer than 5:00" >&2; exit 1; }
[[ "$size" == "1920x1080" ]] || { echo "FAIL: not 1920x1080" >&2; exit 1; }
echo "OK"
