# TrayAgent demo video script (≤ 5:00, 1080p, English, no music)

Source of truth: `segments.yaml` (build.sh reads it). Edit both together.
Segment lengths follow the narration (Polly neural, about 150 words per minute). The build
refuses to render anything longer than 5:00. The previous rehearsal came to about 2:45 plus the team intro.

| # | Segment | What is on screen | Narration |
|---|---|---|---|
| 1 | `intro` | Owner's team intro clip (`raw/team_intro.mp4`, up to 30 s), or a title card | (team intro audio) |
| 2 | `problem` | Slide: the problem | Every day, jewelry stores count every display tray by eye. It is slow, and it misses shrink. A single photo and a single detector pass are not enough: gold reflects the ceiling lights, phones blur, and trays are packed with small items. And a wrong automatic count is worse than no count, because it silently changes inventory. TrayAgent treats counting as a decision, not a guess. |
| 3 | `tray_a` | Phone recording, tray A: the form, upload, live agent timeline, auto-accept | Tray A is a clean photo. The agent first checks the photo with OpenCV: sharpness, glare, and whether the tray is in frame. It straightens the tray with a homography, then counts with a YOLOX model running on the OpenCV 5 DNN engine. The count matches the point-of-sale figure, the evidence is confident, so the agent accepts it. Nothing in inventory changes. |
| 4 | `tray_b` | Phone recording, tray B: glare → re-shot card with instructions → retake → accepted | Tray B has glare. OpenCV's highlight mask shows the reflection hiding part of the tray, so instead of guessing, the agent asks the staff member for a specific re-shot: tilt the phone about fifteen degrees away from the light. The new photo is clean, the count matches, and the re-shot is linked to the first attempt in the audit trail. |
| 5 | `tray_c` | Phone recording, tray C: dense tray, POS mismatch → timeline (tile/zoom/compare) → escalated → review page → manager approves | Tray C is dense, and its count disagrees with the point-of-sale system. Because the items are small and crowded, the agent re-detects on overlapping tiles and zooms into the regions it is unsure about. The count is still one short, so it aligns yesterday's approved photo with feature matching and a homography, and diffs the two. One changed region pinpoints the missing piece. The agent does not decide on its own: it escalates, with the evidence, and a manager approves. |
| 6 | `architecture` | Slide: `docs/competition/architecture.png` + bullets | Under the hood, eight OpenCV 5 tools run inside a bounded loop of at most five steps and twenty seconds. Each tool's output decides the next action. The whole system runs on an AWS Graviton instance, with evidence in S3 and agent metrics and alarms in CloudWatch. Every tool call, reason and latency is traced. |
| 7 | `results` | Slide: numbers from `reports/agentic/summary.json` (shows 'pending' until the real test set exists) | We evaluated on a frozen test set of real tray photos, never used for training or tuning. These are the measured numbers, including the failure cases, which are all in the report. |
| 8 | `limits` | Slide: limitations and responsible use | TrayAgent is honest about its limits. It was trained on a small set of photos from one store, so its numbers will change with more data. A human approves every count that changes inventory. Faces are blurred before anything is stored, and evidence expires after thirty days. Thank you. |

## Rules for the narration

- Say only what the recording shows. After `record.py`, check `clips/record_log.json`, which lists tray C's real tool path, and edit `tray_c` if the run did not tile or zoom.
- Never read out a number that is not in `reports/agentic/RESULTS.md` (from the frozen real test set).
- No music. Keep the subtitles (`trayagent_demo.srt`) in sync by rebuilding after any edit.
