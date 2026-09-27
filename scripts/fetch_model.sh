#!/usr/bin/env bash
# Fetch the TrayAgent ONNX detector and verify its SHA-256 before use.
#
#   scripts/fetch_model.sh                       # uses models/trayagent_v1.source
#   MODEL_SOURCE=s3://bucket/models/trayagent_v1.onnx scripts/fetch_model.sh
#   MODEL_SOURCE=https://.../trayagent_v1.onnx scripts/fetch_model.sh
#   MODEL_SOURCE=/path/to/trayagent_v1.onnx scripts/fetch_model.sh
#
# The expected digest is committed in models/<name>.sha256 (written by
# training/train_yolox.py export). A mismatch aborts and leaves no model behind.
set -euo pipefail

NAME="${MODEL_NAME:-trayagent_v1}"
DIR="${MODEL_DIR:-models}"
SUM_FILE="$DIR/$NAME.sha256"
SRC="${MODEL_SOURCE:-}"
if [[ -z "$SRC" && -f "$DIR/$NAME.source" ]]; then
  SRC="$(tr -d '[:space:]' < "$DIR/$NAME.source")"
fi
if [[ -z "$SRC" ]]; then
  echo "fetch_model: set MODEL_SOURCE (s3://…, https://… or a local path) or create $DIR/$NAME.source" >&2
  exit 2
fi
if [[ ! -f "$SUM_FILE" ]]; then
  echo "fetch_model: missing $SUM_FILE (the committed checksum); refusing to install an unverified model" >&2
  exit 2
fi
expected="$(awk '{print $1}' "$SUM_FILE")"

mkdir -p "$DIR"
tmp="$(mktemp "$DIR/.${NAME}.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
case "$SRC" in
  s3://*) aws s3 cp --only-show-errors "$SRC" "$tmp" ;;
  http://*|https://*) curl -fsSL --retry 3 -o "$tmp" "$SRC" ;;
  *) cp "$SRC" "$tmp" ;;
esac

actual="$(sha256sum "$tmp" | awk '{print $1}')"
if [[ "$actual" != "$expected" ]]; then
  echo "fetch_model: SHA-256 mismatch for $SRC" >&2
  echo "  expected $expected" >&2
  echo "  actual   $actual" >&2
  exit 1
fi
mv "$tmp" "$DIR/$NAME.onnx"
trap - EXIT
echo "fetch_model: $DIR/$NAME.onnx verified (sha256 $actual)"
if [[ ! -f "$DIR/$NAME.json" ]]; then
  echo "fetch_model: warning: sidecar $DIR/$NAME.json missing; the detector will assume YOLOX defaults" >&2
fi
