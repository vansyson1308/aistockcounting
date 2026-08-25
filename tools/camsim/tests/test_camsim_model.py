import numpy as np
import pytest

from tools.camsim.model import CameraSpec, PitchSpec, pitch_grid


def _cam(height=15.0, hfov=62.0, k1=0.0, aim=(0.0, 0.0, 0.0)):
    return CameraSpec(
        name="t",
        width_px=3840,
        height_px=2160,
        hfov_deg=hfov,
        position=np.array([0.0, -42.0, height]),
        aim_at=np.array(aim),
        k1=k1,
    )


def test_aimed_point_projects_to_principal_point():
    cam = _cam()
    pix, vis = cam.project(np.array([[0.0, 0.0, 0.0]]))
    assert vis[0]
    assert pix[0, 0] == pytest.approx(1920, abs=1.0)
    assert pix[0, 1] == pytest.approx(1080, abs=1.0)


def test_point_behind_camera_invisible():
    cam = _cam()
    _, vis = cam.project(np.array([[0.0, -100.0, 0.0]]))
    assert not vis[0]


def test_point_outside_fov_invisible():
    cam = _cam(hfov=30.0)
    _, vis = cam.project(np.array([[52.0, 34.0, 0.0]]))  # far corner
    assert not vis[0]


def test_px_per_m_decreases_with_distance():
    cam = _cam()
    near = np.array([[0.0, -10.0, 0.0]])  # both well inside the FOV
    far = np.array([[0.0, 30.0, 0.0]])
    assert cam.vertical_px_per_m(near)[0] > cam.vertical_px_per_m(far)[0]


def test_vertical_scale_matches_analytic_pinhole():
    """Camera looking horizontally at an object straight ahead:
    projected height of 1 m ≈ f_px / distance."""
    cam = CameraSpec(
        name="t",
        width_px=3840,
        height_px=2160,
        hfov_deg=60.0,
        position=np.array([0.0, -50.0, 1.0]),
        aim_at=np.array([0.0, 50.0, 1.0]),  # level optical axis
    )
    f_px = (3840 / 2) / np.tan(np.radians(30.0))
    d = 60.0
    got = cam.vertical_px_per_m(np.array([[0.0, 10.0, 0.0]]))[0]
    assert got == pytest.approx(f_px / d, rel=0.02)


def test_elevation_angle_analytic():
    cam = _cam(height=20.0)
    pt = np.array([[0.0, -42.0 + 40.0, 0.0]])  # 40 m horizontal from mast
    expected = np.degrees(np.arctan2(20.0, 40.0))
    assert cam.elevation_deg(pt)[0] == pytest.approx(expected, abs=1e-6)


def test_barrel_distortion_shrinks_edge_scale():
    ideal = _cam(hfov=100.0, k1=0.0, height=12.0)
    barrel = _cam(hfov=100.0, k1=-0.15, height=12.0)
    edge_point = np.array([[45.0, 0.0, 0.0]])  # far toward a corner
    assert (
        barrel.vertical_px_per_m(edge_point)[0]
        < ideal.vertical_px_per_m(edge_point)[0]
    )


def test_vertical_axis_rejected():
    with pytest.raises(ValueError):
        CameraSpec(
            name="bad",
            width_px=100,
            height_px=100,
            hfov_deg=60,
            position=np.array([0.0, 0.0, 10.0]),
            aim_at=np.array([0.0, 0.0, 0.0]),
        )


def test_pitch_grid_covers_dimensions():
    pts = pitch_grid(PitchSpec(), step_m=1.0)
    assert pts.shape == (106 * 69, 3)
    assert pts[:, 0].min() == pytest.approx(-52.5)
    assert pts[:, 0].max() == pytest.approx(52.5)
    assert np.all(pts[:, 2] == 0)
