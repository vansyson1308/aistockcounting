# Demo video runbook

Output: `demo/video/trayagent_demo.mp4` (1920×1080, H.264/AAC, ≤ 5:00, no music), plus
`demo/video/trayagent_demo.srt` (English), which is also muxed in as a soft subtitle track.

## Prerequisites (once)
```bash
make backend-venv                      # .venv with Playwright, PyYAML, Pillow
sudo apt-get install -y ffmpeg fonts-dejavu-core   # espeak-ng only for offline placeholder narration
```
Playwright uses the pre-installed Chromium (`/opt/pw-browsers`) or `python -m playwright install chromium`.
Polly needs AWS credentials with `polly:SynthesizeSpeech` (the same account as the deployment is fine).

## 1. Put the inputs in place
| Input | Path |
|---|---|
| Team intro (you record it; ≤ 30 s, landscape, any resolution) | `demo/video/raw/team_intro.mp4` |
| Demo tray photos (real) | `datasets/vj_items/images/demo/{A_clean,B_glare,B_reshot,C_dense,C_prev}.jpg`, placed there by `tools/labeling/ingest_raw.py` from `raw/demo/` |
| POS counts and the true count of `C_prev` | `demo/video/demo.yaml` |
| Live endpoint | `base_url` in `demo/video/demo.yaml`, or the `BASE_URL` env var (the CloudFront URL from `scripts/aws/deploy.sh`) |
| Final numbers | `reports/agentic/summary.json` from `make eval-agent` (the results slide reads it) |

## 2. Record and render
```bash
RECORD=1 BASE_URL=https://<your>.cloudfront.net demo/video/build.sh
```
The build runs four steps:
1. Slides.
2. Playwright records trays A, B and C in an iPhone 13 viewport.
3. Polly narration.
4. ffmpeg composition, followed by an `ffprobe` check that the video is 1920×1080 and ≤ 300 s. The build fails otherwise.

Check `demo/video/clips/record_log.json`:
- A should be `auto_accept`.
- B should be `request_recapture` followed by `auto_accept`.
- C should be `escalate` with `approved: true`.

If a scenario did something else (for example, B's re-shot still had glare), retake that photo and run
`RECORD=1 ... build.sh` again. If C's `tools` list does not include `tile_detect`/`zoom_recount`,
edit the `tray_c` narration and bullets in `demo/video/segments.yaml` to match the real trace.

## 3. Re-render after adding your intro, without re-recording
```bash
demo/video/build.sh            # reuses clips/, re-renders slides, narration and the video
```

## 4. Watch it once, then upload
- Watch the whole video, and check that every sentence matches the screen.
- Upload to YouTube (Unlisted or Public) or Vimeo. Upload `trayagent_demo.srt` as English captions.
- Paste the link into Devpost (`docs/competition/DEVPOST_SUBMISSION.md`).

## Options
| Variable | Default | Meaning |
|---|---|---|
| `TTS` | `polly` | `espeak` = offline robotic placeholder |
| `POLLY_VOICE` | `Matthew` | any Polly neural English voice, e.g. `Joanna`, `Ruth` |
| `AWS_REGION` | `us-east-1` | Polly region |
| `WATERMARK` | empty | text stamped on every slide (for rehearsals) |
| `DEMO_DIR` | from demo.yaml | alternate photo folder (rehearsals) |

## Rehearsal status (2026-09-25)
The pipeline was rendered end to end in the dev container:
- It used synthetic trays, a local docker stack and espeak narration, and was watermarked "PIPELINE TEST: SYNTHETIC TRAYS".
- Result: 165.2 s, 1920×1080, H.264, AAC and mov_text subtitle streams, verified with `ffprobe`.
- It is not the submission video. The real one needs your photos, the AWS endpoint and your intro.
