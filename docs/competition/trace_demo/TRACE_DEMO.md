# Trace demonstration: OpenCV output drives the agent's next action

> Source: SYNTHETIC test fixture (procedurally drawn tray, OpenCV classical baseline detector; true count 89, stale POS 90). Regenerate from the real demo tray C with: python scripts/export_trace_demo.py api --base-url <endpoint> --scan-id <id>

Final decision: **escalate**. Escalate to a human: single-shot and tiled counts disagree in 2 cell(s) (single 91, final 90).

| # | Step | Tool (OpenCV 5) | Key outputs | Decision it led to | Why (the policy's reason) | ms | Evidence |
|---|---|---|---|---|---|---|---|
| 1 | 1 | `assess_quality` | blur_var=2732.54, glare_ratio=0.0092, tray_coverage=0.9902, flags=[] | `assess_quality` | Start by checking image quality. | 134 | [img](evidence/01_assess_quality.jpg) |
| 2 | 2 | `rectify_tray` | found=True, method=given, out_size=[1278, 958] | `count` | Quality is acceptable: rectify the tray and detect. | 6 | [img](evidence/02_rectify_tray.jpg) |
| 3 | 2 | `detect` | count=91, mean_conf=0.9246, uncertain=0, median_box_frac=0.0004, crowding=0.022 | `count` | Quality is acceptable: rectify the tray and detect. | 109 | [img](evidence/03_detect.jpg) |
| 4 | 3 | `tile_detect` | count=89, grid=[3, 4], disagreement_cells=[[319, 0, 319, 319], [639, 319, 319, 319]] | `tile_detect` | Dense tray (count=91, median box=0.00036, crowding=0.02): re-detect on overlapping tiles. | 1918 | [img](evidence/04_tile_detect.jpg) |
| 5 | 4 | `zoom_recount` | count_before=89, count=90, unresolved=0 | `zoom_recount` | 2 uncertain region(s): zoom in and recount them. | 262 | [img](evidence/05_zoom_recount.jpg) |
| 6 | final | `render_evidence` | boxes=90, uncertain_regions=0, changed_regions=0 | `escalate` | Escalate to a human: single-shot and tiled counts disagree in 2 cell(s) (single 91, final 90). | 2 | [img](evidence/06_render_evidence.jpg) |

## Causal chain

1. **assess_quality**: Start by checking image quality.
1. **count**: Quality is acceptable: rectify the tray and detect.
1. **tile_detect**: Dense tray (count=91, median box=0.00036, crowding=0.02): re-detect on overlapping tiles.
1. **zoom_recount**: 2 uncertain region(s): zoom in and recount them.
1. **escalate**: Escalate to a human: single-shot and tiled counts disagree in 2 cell(s) (single 91, final 90).

Each reason quotes the OpenCV measurement that triggered the next action (for
example the glare ratio, the crowding, uncertain regions, or the count vs POS).
The last step is always `render_evidence`: the annotated sheet a human approves from.
