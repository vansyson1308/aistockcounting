# Devpost submission: fields ready to paste

Challenge: OpenCV AI Competition 2026, powered by AWS (https://opencv26.devpost.com/).
Deadline: 2026-10-26 23:59 PT (27 Oct 13:59 Vietnam time; Devpost shows the exact cutoff).

Before pasting, replace every `<…>` placeholder. Paste the numbers in "Accomplishments"
**only** from `reports/agentic/RESULTS.md` (the frozen real test set).

---

**Project name**
TrayAgent

**Elevator pitch** (≤ 200 characters)
A phone photo of a jewelry tray becomes a verified count: an OpenCV 5 agent on AWS Graviton re-shoots, tiles, zooms and compares until it is sure, or asks a human.

**Awards applied for**
Overall; Agentic Vision Award; (Best Use of COOL only if the COOL benchmark in `reports/cool/` was run).

**Video demo link**
`<YouTube/Vimeo URL of demo/video/trayagent_demo.mp4>`

**Try it out**
- Live app (mobile): `<https://xxxx.cloudfront.net/scan>` (demo tenant)
- Code: `<GitHub repo URL, or "source archive attached (trayagent_source.zip)">`

**Built with** (tags)
opencv, opencv-5, python, fastapi, yolox, onnx, aws, amazon-ec2, aws-graviton, amazon-s3, amazon-cloudwatch, amazon-cloudfront, amazon-ecr, aws-cdk, amazon-bedrock (optional planner), amazon-polly (video narration), postgresql, next.js, typescript, docker, playwright

---

## About the project

### Inspiration
Every day, jewelry shops count every display tray by eye. Our store does it with photos
in a chat group and a spreadsheet. It is slow, and a missing ring is found days later.
We tried a single detector and learned the real problem: gold reflects the ceiling
lights, phones blur, and trays are packed. **A wrong automatic count is worse than no
count**, because it quietly changes inventory. We wanted a counter that knows when it
is unsure and does something about it.

### What it does
Staff take a photo on their phone. TrayAgent runs a bounded perception → decision →
action loop (at most 5 steps and 20 seconds) with eight OpenCV 5 tools:
- `assess_quality`: blur (Laplacian variance), glare (HSV highlight mask), exposure, tray coverage;
- `rectify_tray`: contour quad + homography;
- `detect`: YOLOX ONNX on the OpenCV 5 DNN engine, `NMSBoxes`;
- `tile_detect`: overlapping tiles with a global NMS merge for dense trays;
- `zoom_recount`: crop, upscale and re-detect uncertain regions;
- `reduce_glare`: inpainting + CLAHE;
- `compare_previous`: ORB/SIFT + RANSAC homography + absdiff against yesterday's approved photo;
- `render_evidence`: the annotated sheet a human approves from.

What OpenCV measures decides the next action:
- glare leads to a specific re-shot instruction;
- crowding leads to tiling;
- low confidence leads to zooming;
- a mismatch with the POS count leads to a comparison with yesterday, then a human.

The agent **auto-accepts only when inventory would not change** (the count equals POS
and every piece of evidence is confident). Otherwise a manager approves, corrects or
rejects, from annotated evidence. Every tool call is traced (inputs, outputs, evidence
image, decision, reason, latency) and audited.

### How we built it
- **Vision:** OpenCV 5.0 (`opencv-python-headless==5.0.0.93`) for all image analysis and
  inference (`cv2.dnn.readNetFromONNX` with `ENGINE_AUTO`), and YuNet
  (`cv2.FaceDetectorYN`) to blur faces before storage.
- **Detector:** YOLOX (Apache-2.0), trained on our own labelled tray photos:
  - open-vocabulary pre-labels, reviewed by a human in CVAT;
  - a frozen, SHA-256-verified test split;
  - exported to ONNX with a sidecar. No AGPL code in the runtime, enforced by a licence gate.
- **Agent:** a deterministic policy with guardrails, plus an optional Amazon Bedrock
  (Converse tool use) planner that can only choose from the allowed actions and falls
  back on any error.
- **App:** FastAPI + PostgreSQL on our existing inventory "truth layer" (POS reconciliation,
  discrepancy inbox), and a Next.js PWA with a live agent timeline and a review page.
- **AWS:** CDK:
  - an EC2 Graviton (arm64) host running images from ECR;
  - S3 for evidence, with a 30-day lifecycle;
  - CloudWatch for logs, agent metrics (steps, escalation rate, latency) and alarms;
  - CloudFront for HTTPS.

### Challenges we ran into
- **OpenCV 5 module moves:** AKAZE and the Haar cascades are not in the 5.0 main wheel,
  so we switched to ORB/SIFT and YuNet.
- **A false auto-accept found in our own trace review:** a glare highlight looked like
  a ring. Tiling dropped it correctly, but zoom re-confirmed it and the count matched a
  stale POS number. We added a "view conflict" guard: when two views of the same tray
  disagree, a human decides.
- **Honest evaluation with a small dataset:** a frozen test manifest that the eval script
  verifies before it runs.

### Accomplishments that we're proud of
- `<paste from reports/agentic/RESULTS.md: exact-count accuracy single shot → TrayAgent, count MAE, mAP@0.5, false auto-accept rate, escalation rate, p50/p95 latency on Graviton>`
- The approval gate cannot be bypassed: the review, discrepancy resolution and agent
  re-run routes all refuse a scan awaiting approval, and tests prove it.
- Every decision is explainable: the trace quotes the measurement behind each action.

### What we learned
Counting is a decision problem, not a detection problem. The value came from knowing
*when not to trust* a count, and from making the cheapest fix (a better photo) the
default.

### What's next
- More stores and tray types; calibrating the policy thresholds per store.
- SKU-level recognition.
- Writing approved counts back to POS.
- COOL/KleidiCV acceleration on Graviton4.

---

## Additional questions (if the form asks)

**How does your project use OpenCV 5?**
All image analysis and inference runs on OpenCV 5.0: quality assessment, rectification,
DNN inference (the new engine selector), NMS, tiling, zoom, glare inpainting,
feature-based alignment and diffing, evidence rendering, and face blurring. `/health`
reports the OpenCV version, and a test asserts that it is 5.x.

**What runs on AWS?**
- The whole application runs on an EC2 Graviton (arm64) instance, from ECR images.
- Evidence images are in S3 (with a lifecycle policy).
- Metrics and alarms are in CloudWatch, and HTTPS is served through CloudFront.
- Optional: Bedrock for the planner, and Polly for the video narration.

**Agentic Vision: where does OpenCV output change a later action?**
See `docs/competition/trace_demo/TRACE_DEMO.md` and the video (tray B: the glare ratio
leads to a re-shot request; tray C: crowding leads to tiling, uncertainty to zooming, and
the POS mismatch to `compare_previous`, then an escalation that a human approves).

**Responsible AI**
- A human approves every count that changes inventory.
- There is a full audit trail.
- Faces are blurred before storage, and data expires after 30 days.
- The limitations are documented in the technical report.
