# Decisions log

Format: ID, date, decision, why, and what it deviates from (if anything).

| ID | Date | Decision | Why / deviation |
|---|---|---|---|
| D-001 | 2026-09-25 | `docs/competition/SPEC.md` was authored from the mission brief. | The mission names SPEC.md as the source of truth, but it did not exist in the repo. §4.4 (policy), §7 (gates) and §9 (video) are therefore defined by us from the brief. |
| D-002 | 2026-09-25 | Work happens on `claude/relaxed-wozniak-nhlyvm`, not `opencv-comp`. | The session harness only allows pushes to its designated branch. This branch plays the role of `opencv-comp`. The owner can rename it on GitHub (`git push origin claude/relaxed-wozniak-nhlyvm:opencv-comp`). |
| D-003 | 2026-09-25 | Football-pivot directories (`ml/`, `reports/gate0a/`, `tools/camsim/`) stay in the tree until the owner approves their removal (Checkpoint A item 3). | Removal needs owner approval, and creating a `football-pivot` branch means pushing to a branch outside the session's allowed set. The competition runtime does not import them, and the license gate treats them as a separate surface. |
| D-004 | 2026-09-25 | Pinned `opencv-python-headless==5.0.0.93` (verified on PyPI 2026-09-25; manylinux x86_64 and aarch64 wheels exist). | Required by the rules. The headless build avoids GUI/X11 libraries in the container. |
| D-005 | 2026-09-25 | Budget "step" = one controller decision that runs perception tools. The terminal action (accept / recapture / escalate + `render_evidence`) is not a step. `rectify_tray` + `detect` share one step. | Lets the hardest demo path (assess → count → tile → zoom → compare → escalate) fit in the mandated 5 steps while still tracing every tool call individually. See SPEC §4.4. |
| D-006 | 2026-09-25 | Detector backends: `onnx` (YOLOX via `cv2.dnn`, the product path), `classical` (OpenCV-only highlight/contour baseline, no learned weights) and `mock` (tests only). Mock is used only when `DETECTOR_BACKEND=mock` or `MOCK_MODE=true` is set explicitly. | The mission requires mock mode to be explicit only. The classical baseline keeps the whole agent demo-able before weights exist, and is labelled as such in `/health` and in every trace. It is never reported as the product model. |
| D-007 | 2026-09-25 | HTTPS via CloudFront in front of the Graviton instance. | This gives a valid TLS certificate without owning a domain or running certbot. It is inside the free tier for demo traffic. |
