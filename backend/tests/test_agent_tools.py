"""Unit tests for every OpenCV 5 agent tool (synthetic fixtures; tests only)."""

import json

import numpy as np
import pytest

from app.agent.tools import (
    TOOL_NAMES,
    assess_quality,
    compare_previous,
    detect,
    rectify_tray,
    reduce_glare,
    regions_from_dets,
    render_evidence,
    tile_detect,
    zoom_recount,
)
from app.agent.tools.tile_detect import choose_grid, make_tiles, merge_tile_dets
from app.services.detector_cv import ClassicalDetector, Det
from tests.fixtures.synth_tray import make_tray


def _json_safe(out: dict) -> None:
    json.dumps(out)  # every tool's trace outputs must serialise


def test_tool_catalogue() -> None:
    assert set(TOOL_NAMES) == {
        "assess_quality",
        "rectify_tray",
        "detect",
        "tile_detect",
        "zoom_recount",
        "reduce_glare",
        "compare_previous",
        "render_evidence",
    }


def test_assess_quality_clean_and_glare() -> None:
    clean = assess_quality(make_tray().image)
    assert clean.flags == () and clean.tray_quad is not None
    assert clean.evidence is not None and clean.evidence.ndim == 3
    _json_safe(clean.outputs())
    glare = assess_quality(make_tray(glare=0.2).image)
    assert "glare" in glare.flags
    assert glare.metrics["glare_ratio"] > clean.metrics["glare_ratio"]


def test_rectify_tray_recovers_perspective() -> None:
    tray = make_tray(perspective=0.15, seed=1)
    res = rectify_tray(tray.image)
    assert res.found and res.method == "contour"
    assert np.abs(res.quad - tray.tray_quad).max() < 8
    assert detect(res.image, ClassicalDetector()).count == tray.count
    _json_safe(res.outputs())


def test_rectify_tray_without_tray_returns_identity() -> None:
    img = np.full((400, 600, 3), 128, np.uint8)
    res = rectify_tray(img)
    assert not res.found
    assert np.array_equal(res.homography, np.eye(3))
    assert res.image is img


def test_detect_reports_crowding_and_uncertainty() -> None:
    class Fixed:
        name, version = "fixed", "t"

        def detect(self, img):
            return [
                Det(10, 10, 20, 20, 0.9),
                Det(25, 10, 20, 20, 0.3),
                Det(300, 300, 20, 20, 0.8),
            ]

    res = detect(np.zeros((400, 400, 3), np.uint8), Fixed())
    assert res.count == 3
    assert res.uncertain_idx == (1,)
    assert res.crowding == pytest.approx(2 / 3)
    _json_safe(res.outputs())


def test_tile_grid_and_tiles_cover_image() -> None:
    assert choose_grid((960, 1280), 0.0003, 100)[1] >= 3
    tiles = make_tiles((960, 1280), (2, 2), 0.2)
    assert len(tiles) == 4
    covered = np.zeros((960, 1280), bool)
    for x, y, w, h in tiles:
        covered[y : y + h, x : x + w] = True
    assert covered.all()


def test_merge_drops_truncated_and_duplicate_boxes() -> None:
    shape = (100, 200)
    t1, t2 = (0, 0, 120, 100), (80, 0, 120, 100)
    d_full = Det(90, 40, 20, 20, 0.9)  # item at x=90..110 lies in the overlap
    per_tile = [
        (t1, [Det(90, 40, 20, 20, 0.9)]),
        (t2, [Det(10, 40, 20, 20, 0.85)]),  # the same item seen from tile 2
        (t1, [Det(110, 70, 10, 10, 0.8)]),  # touches tile 1's inner right edge: dropped
    ]
    merged = merge_tile_dets(per_tile, shape)
    assert len(merged) == 1
    assert merged[0].x == pytest.approx(d_full.x)


def test_tile_detect_recovers_small_items_missed_at_full_frame() -> None:
    tray = make_tray(n_items=120, item_radius=(7, 9), seed=2)
    det = ClassicalDetector(input_side=640)
    single = detect(tray.image, det)
    assert single.count < tray.count
    tiled = tile_detect(
        tray.image, det, single_shot=single.dets, median_box_frac=single.median_box_frac
    )
    assert abs(tiled.count - tray.count) <= 2
    assert tiled.count > single.count
    assert len(tiled.tile_counts) == tiled.grid[0] * tiled.grid[1]
    _json_safe(tiled.outputs())


def test_zoom_recount_resolves_uncertain_region() -> None:
    class ZoomSensitive:
        """Weak at 1x, confident when the crop is upscaled (a real CNN's resolution effect)."""

        name, version = "zs", "t"

        def detect(self, img):
            conf = 0.9 if img.shape[0] > 300 else 0.3
            h, w = img.shape[:2]
            return [Det(w / 2 - 10, h / 2 - 10, 20, 20, conf)]

    img = np.zeros((1000, 1000, 3), np.uint8)
    base = [Det(490, 490, 20, 20, 0.3), Det(100, 100, 20, 20, 0.95)]
    regions = regions_from_dets(base, (0,), img.shape[:2])
    res = zoom_recount(img, ZoomSensitive(), regions, base, zoom=3.0)
    assert res.regions[0].resolved
    assert res.unresolved == ()
    assert res.count == 2
    assert min(d.conf for d in res.dets) >= 0.9
    _json_safe(res.outputs())


def test_zoom_recount_keeps_unresolved_region() -> None:
    class AlwaysWeak:
        name, version = "weak", "t"

        def detect(self, img):
            h, w = img.shape[:2]
            return [Det(w / 2 - 10, h / 2 - 10, 20, 20, 0.3)]

    img = np.zeros((600, 600, 3), np.uint8)
    base = [Det(290, 290, 20, 20, 0.3)]
    res = zoom_recount(
        img, AlwaysWeak(), regions_from_dets(base, (0,), img.shape[:2]), base
    )
    assert not res.regions[0].resolved
    assert len(res.unresolved) == 1
    assert res.count == 1  # the original detection is kept


def test_reduce_glare_lowers_glare_and_removes_false_items() -> None:
    tray = make_tray(glare=0.03, seed=4)
    before = detect(tray.image, ClassicalDetector()).count
    res = reduce_glare(tray.image)
    assert res.glare_after < res.glare_before
    after = detect(res.image, ClassicalDetector()).count
    assert abs(after - tray.count) < abs(before - tray.count)
    assert res.image.shape == tray.image.shape
    _json_safe(res.outputs())


def test_compare_previous_finds_removed_item() -> None:
    prev = make_tray(n_items=16, seed=7)
    curr = make_tray(n_items=16, seed=7, exclude_items=[5], perspective=0.06)
    res = compare_previous(curr.image, prev.image)
    assert res.aligned and res.inliers >= 15
    assert len(res.regions) == 1
    # the changed region sits where item 5 was
    x, y, w, h = res.regions[0]
    cx, cy = x + w / 2, y + h / 2
    missing = [
        b
        for i, b in enumerate(make_tray(n_items=16, seed=7, perspective=0.06).boxes)
        if i == 5
    ][0]
    assert missing[0] <= cx <= missing[0] + missing[2]
    assert missing[1] <= cy <= missing[1] + missing[3]
    _json_safe(res.outputs())


def test_compare_previous_no_change_and_alignment_failure() -> None:
    prev = make_tray(n_items=16, seed=7)
    same = make_tray(n_items=16, seed=7, perspective=0.06)
    res = compare_previous(same.image, prev.image)
    assert res.aligned and res.regions == () and res.changed_ratio < 0.001
    flat = np.full((500, 500, 3), 90, np.uint8)
    fail = compare_previous(flat, prev.image)
    assert not fail.aligned and fail.homography is None


def test_render_evidence_sheet() -> None:
    img = make_tray().image
    sheet = render_evidence(
        img,
        [Det(10, 10, 30, 30, 0.9)],
        headline="ESCALATE: count 11 vs POS 12",
        details=["compare_previous: 1 changed region"],
        uncertain_regions=[(100, 100, 50, 50)],
        changed_regions=[(300, 300, 60, 60)],
        diff_heatmap=img,
    )
    assert sheet.evidence is not None and sheet.evidence.shape[1] > img.shape[1] // 2
    assert sheet.outputs() == {"boxes": 1, "uncertain_regions": 1, "changed_regions": 1}
