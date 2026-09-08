"""Offline end-to-end smoke of the cloud orchestration (Stage 0 analyze → 1 → 2)
on a tiny SYNTHETIC video with a FAKE detector/embedder.

This validates software mechanics only (paths, caching, scoring plumbing,
report generation). It is never football-product evidence.
"""

import json
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
pytest.importorskip("trackeval")

from ml.gate0a.cloud import stage0, stage1, stage2  # noqa: E402
from ml.gate0a.cloud.contract import load_contract  # noqa: E402
from ml.gate0a.cloud.run_stage import REPO_ROOT, load_config  # noqa: E402

FPS, N, W, H = 25, 220, 640, 360
COLORS = [(200, 30, 30), (30, 30, 200), (220, 220, 40), (40, 200, 200), (200, 40, 200), (250, 250, 250)]


def _positions(f, i):
    t = f / FPS
    if 3.0 <= t < 5.0:  # dense clump
        cx = 300 + 9 * i + 2 * np.sin(t * 3 + i)
    else:
        cx = 60 + 95 * i + 25 * np.sin(t * 1.5 + i)
    cy = 180 + 30 * np.cos(t + i)
    h = 30 if not (6.5 <= t < 8.0) else 14
    return int(cx), int(cy), 12, h


def _make_fixture(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    video = root / "half.avi"
    vw = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), FPS, (W, H))
    gt_rows = []
    gsr = {"info": {}, "images": [], "categories": [], "annotations": []}
    for f in range(1, N + 1):
        img = np.full((H, W, 3), (40, 140, 40), np.uint8)
        for i, color in enumerate(COLORS):
            cx, cy, w, h = _positions(f, i)
            cv2.rectangle(img, (cx, cy), (cx + w, cy + h), color, -1)
            gt_rows.append(f"{f},{i + 1},{cx},{cy},{w},{h},1,1,1")
            gsr["annotations"].append({
                "image_id": f"3{f:06d}", "track_id": 100 + i, "supercategory": "object",
                "attributes": {"role": "player", "team": "left" if i < 3 else "right"},
                "bbox_image": {"x": cx, "y": cy, "w": w, "h": h}})
        gt_rows.append(f"{f},99,600,300,30,30,0,1,1")  # ignore region row
        vw.write(img)
    vw.release()
    (root / "gt.txt").write_text("\n".join(gt_rows) + "\n")
    (root / "seqinfo.ini").write_text(f"[Sequence]\nname=test\nframeRate={FPS}\nseqLength={N}\nimWidth={W}\nimHeight={H}\n")
    (root / "gsr.json").write_text(json.dumps(gsr))
    return video


class FakeDetector:
    def __init__(self):
        from ml.gate0a.cloud.detector_adapter import DetectorProfile

        self.profile = DetectorProfile()
        self.rng = np.random.default_rng(0)

    def detect_frame(self, img_rgb, window=""):
        # A fake "detector": finds saturated colored blobs by thresholding the
        # actual pixels (software plumbing only, never product evidence).
        mask = (np.abs(img_rgb.astype(int) - np.array([40, 140, 40])).sum(axis=2) > 120).astype(np.uint8)
        n, _lab, stats, _cent = cv2.connectedComponentsWithStats(mask)
        boxes, scores = [], []
        for k in range(1, n):
            x, y, w, h, area = stats[k]
            if area < 30:
                continue
            boxes.append([x, y, x + w, y + h])
            scores.append(0.6 + 0.35 * self.rng.random())
        self.profile.frames += 1
        self.profile.tiles += 1
        self.profile.seconds += 1e-3
        return np.array(boxes, dtype=float).reshape(-1, 4), np.array(scores)

    def describe(self):
        return {"hf_id": "fake/blob-detector", "revision": "0", "weights_sha256": "none",
                "tile_px": 640, "overlap_px": 0, "nms_iou": 0.6, "model_input_px": 640, "precision": "fp32"}


class FakeEmbedder:
    def __init__(self):
        from ml.gate0a.cloud.reid_adapter import EmbedProfile

        self.profile = EmbedProfile()

    def embed(self, img_rgb, boxes):
        keep, vecs = [], []
        for i, b in enumerate(boxes):
            x1, y1, x2, y2 = (int(v) for v in b)
            crop = img_rgb[max(0, y1):y2, max(0, x1):x2]
            if crop.size == 0:
                continue
            v = crop.reshape(-1, 3).mean(axis=0).astype(np.float32) + 1e-3
            keep.append(i)
            vecs.append(v / np.linalg.norm(v))
        self.profile.crops += len(keep)
        self.profile.seconds += 1e-3
        return np.array(keep, dtype=int), (np.stack(vecs) if vecs else np.zeros((0, 3), np.float32))

    def describe(self):
        return {"arch": "fake-mean-color", "weights": "none", "weights_sha256": "none", "crop_hw": [8, 4]}


def test_stage012_offline_smoke(tmp_path):
    fixture = tmp_path / "fixture"
    video = _make_fixture(fixture)
    out = tmp_path / "out"
    cfg = load_config()
    cfg["windows"].update({"clip_seconds": 2.0, "tune_seconds": 1.0, "candidate_stride_seconds": 1.0})
    cfg["storage"]["export_clips"] = False
    cfg["reid_diag"]["deltas_frames"] = [5, 25]
    contract = load_contract()
    acq = {"gt_path": str(fixture / "gt.txt"), "gt_scope": "per_match", "video_path": str(video),
           "video_scope": "per_half", "video_identity": {"path": "videos/test.avi", "size": 1, "lfs_sha256": None},
           "seqinfo_path": str(fixture / "seqinfo.ini"), "gsr_path": str(fixture / "gsr.json"),
           "dataset_revision": "synthetic"}
    st0 = stage0.analyze(cfg, contract, out, acq)
    assert st0["sanity_all_passed"] and st0["evaluator_units"] == "fraction"
    assert set(st0["windows"]) == {"DENSE", "FAR", "OPEN", "TUNE"}
    assert st0["gsr_link"]["available"] and st0["gsr_link"]["team_labeled_ids"] == 6
    assert st0["gt_stats"]["ignore_rows"] == N

    st1 = stage1.run(cfg, contract, out, lambda: (FakeDetector(), {"name": "fake"}),
                     lambda: (FakeEmbedder(), {"name": "fake"}), device="cpu")
    assert st1["chain_ran"] and st1["selected_margin"] in cfg["tracker"]["ambiguity_margin_grid"]
    assert st1["recall_ge40"] is None or 0.0 <= st1["recall_ge40"] <= 1.0
    for role in ("OPEN", "DENSE", "FAR"):
        assert (out / "cache" / role / "frame_pass.cache.json").exists()
        assert 0.0 <= st1["results"][role]["P4"]["hota"] <= 1.0
    # The blob "detector" resolves separated players; the DENSE clump merges
    # into one blob by construction, so only OPEN/FAR carry a quality floor.
    assert st1["results"]["OPEN"]["P4"]["hota"] > 0.5 and st1["results"]["FAR"]["P4"]["hota"] > 0.5

    # Resume: second call must skip the frame pass (cache valid).
    st1b = stage1.run(cfg, contract, out, lambda: (FakeDetector(), {"name": "fake"}),
                      lambda: (FakeEmbedder(), {"name": "fake"}), device="cpu")
    assert all(v["status"] == "SKIP — CACHE VALID" for v in st1b["pass_summary"]["windows"].values())

    st2 = stage2.run(cfg, contract, out, REPO_ROOT, "2026-01-01T00:00:00+00:00")
    rep = out / "reports" / "gate0a" / "cloud" / "stage012"
    for rel in ("executive_report.md", "maturity.json", "environment.json", "diagnostic_contract.yaml",
                "data_integrity.md", "evaluator_sanity.json", "diagnostic_windows.yaml",
                "artifact_manifest.json", "detector/config.yaml", "detector/px_height_recall.csv",
                "reid/metrics.json", "reid/distance_summary.csv", "real/pipeline_ablation.csv",
                "oracle/oracle_ablation.csv", "bottleneck/diagnosis.json", "bottleneck/diagnosis.md",
                "compute/profile.json"):
        assert (rep / rel).exists(), rel
    text = (rep / "executive_report.md").read_text()
    assert "NOT OFFICIAL GATE 0A VERDICT" in text and "TEST SET UNTOUCHED" in text
    assert st2["maturity"]["maturity"].startswith("LEVEL")
    assert st2["bottleneck"]["dominant"] in {"DETECTION-LIMITED", "REID-LIMITED", "ASSOCIATION-LIMITED",
                                             "TEAM-LIMITED", "MIXED", "NONE-DOMINANT", "UNDETERMINED"}
    manifest = json.loads((rep / "artifact_manifest.json").read_text())
    assert manifest["clip_manifest_sha256"] == st0["windows_sha256"]
