import json

import numpy as np
import pytest

from tools.camsim.model import CameraSpec, PitchSpec
from tools.camsim.occlusion import (
    OcclusionConfig,
    occlusion_events,
    occlusion_rate_by_zone,
    sample_positions,
)
from tools.camsim.presets import PRESETS
from tools.camsim.run import evaluate_rig, main


def _cam(height=15.0):
    return CameraSpec(
        name="t",
        width_px=3840,
        height_px=2160,
        hfov_deg=62.0,
        position=np.array([0.0, -42.0, height]),
        aim_at=np.array([0.0, 0.0, 0.0]),
    )


def test_inline_players_occlude_side_by_side_dont():
    cam = _cam(height=10.0)
    inline = np.array([[0.0, -10.0, 0.0], [0.0, -9.5, 0.0]])
    occ, vis = occlusion_events(cam, inline, overlap_iou=0.3)
    assert vis.all()
    assert occ[0] or occ[1]  # the farther one is covered
    apart = np.array([[-20.0, 0.0, 0.0], [20.0, 0.0, 0.0]])
    occ2, vis2 = occlusion_events(cam, apart, overlap_iou=0.3)
    assert vis2.all()
    assert not occ2.any()


def test_sampler_respects_pitch_bounds_and_count():
    pitch = PitchSpec()
    rng = np.random.default_rng(0)
    for set_piece in (False, True):
        pos = sample_positions(pitch, rng, set_piece)
        assert pos.shape == (22, 3)
        assert np.all(np.abs(pos[:, 0]) <= pitch.length_m / 2)
        assert np.all(np.abs(pos[:, 1]) <= pitch.width_m / 2)


def test_occlusion_grid_deterministic_under_seed():
    cam = _cam()
    pitch = PitchSpec()
    edges_x = np.linspace(-52.5, 52.5, 7)
    edges_y = np.linspace(-34, 34, 5)
    cfg = OcclusionConfig(n_samples=20, seed=11)
    g1, r1 = occlusion_rate_by_zone(cam, pitch, cfg, edges_x, edges_y)
    g2, r2 = occlusion_rate_by_zone(cam, pitch, cfg, edges_x, edges_y)
    assert r1 == r2
    np.testing.assert_array_equal(
        np.nan_to_num(g1, nan=-1), np.nan_to_num(g2, nan=-1)
    )


def test_set_piece_more_occlusion_than_open_play():
    cam = _cam(height=12.0)
    pitch = PitchSpec()
    edges_x = np.linspace(-52.5, 52.5, 3)
    edges_y = np.linspace(-34, 34, 3)
    _, open_rate = occlusion_rate_by_zone(
        cam, pitch, OcclusionConfig(n_samples=60, set_piece=False), edges_x, edges_y
    )
    _, set_rate = occlusion_rate_by_zone(
        cam, pitch, OcclusionConfig(n_samples=60, set_piece=True), edges_x, edges_y
    )
    assert set_rate > open_rate


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_presets_build_and_evaluate(name):
    pitch = PitchSpec()
    rig = PRESETS[name](pitch, height_m=15.0)
    result = evaluate_rig(rig, pitch, grid_step_m=4.0, occlusion_samples=8)
    s = result["summary"]
    assert s["pitch_coverage_fraction"] > 0.9
    assert s["player_bbox_height_px"]["median"] > 0
    assert 0.0 <= s["occlusion_rate_open_play"] <= 1.0


def test_b_beats_a_on_far_side_resolution():
    """The architecture-B rationale in numbers: two 62° cameras deliver more
    far-half pixels than one 100° wide-angle at the same mount."""
    pitch = PitchSpec()
    a = evaluate_rig(PRESETS["A"](pitch, 15.0), pitch, 4.0, occlusion_samples=4)
    b = evaluate_rig(PRESETS["B"](pitch, 15.0), pitch, 4.0, occlusion_samples=4)
    assert (
        b["summary"]["player_bbox_height_px"]["p10"]
        > a["summary"]["player_bbox_height_px"]["p10"]
    )


def test_higher_mount_improves_min_elevation():
    pitch = PitchSpec()
    low = evaluate_rig(PRESETS["B"](pitch, 8.0), pitch, 4.0, occlusion_samples=4)
    high = evaluate_rig(PRESETS["B"](pitch, 20.0), pitch, 4.0, occlusion_samples=4)
    assert (
        high["summary"]["elevation_deg"]["min"]
        > low["summary"]["elevation_deg"]["min"]
    )


def test_cli_writes_summary_json(tmp_path):
    rc = main(
        [
            "--preset",
            "B",
            "--heights",
            "15",
            "--grid-step",
            "6",
            "--occlusion-samples",
            "4",
            "--out",
            str(tmp_path),
        ]
    )
    assert rc == 0
    data = json.loads((tmp_path / "summary.json").read_text())
    assert data[0]["rig"] == "B"
    assert data[0]["mount_height_m"] == 15.0
