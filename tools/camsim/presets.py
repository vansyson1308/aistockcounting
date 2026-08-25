"""Candidate camera configurations (plan section F.2 architectures A-D).

Geometry conventions: world origin at pitch center; sideline masts stand on
the near side at y = -(width/2 + SETBACK_M) — a realistic main-stand roof
setback (an early modeling result of this tool: at small setbacks a single
16:9 camera physically cannot fit the near touchline and the far touchline
in its vertical FOV). Cameras aim at the ground point whose depression angle
bisects the near/far extreme depressions, centering the pitch in the
vertical FOV. Heights, setbacks, and FOVs are the sweep variables — these
presets are starting points for the ranking run, not decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from tools.camsim.model import CameraSpec, PitchSpec

SETBACK_M = 24.0  # mast distance behind the near touchline / goal line
UHD = (3840, 2160)


@dataclass
class RigConfig:
    name: str
    description: str
    cameras: list[CameraSpec] = field(default_factory=list)
    # True when cameras observe from genuinely different viewpoints, so a
    # player clump is "resolved" if ANY camera sees it un-occluded.
    multi_viewpoint: bool = False


def _mast_y(pitch: PitchSpec) -> float:
    return -(pitch.width_m / 2 + SETBACK_M)


def _bisector_ground_distance(height: float, near: float, far: float) -> float:
    """Ground distance whose depression bisects the near/far depressions."""
    mid = (np.arctan2(height, near) + np.arctan2(height, far)) / 2.0
    return height / np.tan(mid)


def _sideline_aim(pitch: PitchSpec, height: float, aim_x: float) -> np.ndarray:
    """Aim point for a near-sideline mast camera: x fixed, y from bisector."""
    near = SETBACK_M
    far = SETBACK_M + pitch.width_m
    d = _bisector_ground_distance(height, near, far)
    return np.array([aim_x, _mast_y(pitch) + d, 0.0])


def _endline_aim(pitch: PitchSpec, height: float, sign: float) -> np.ndarray:
    """Aim point for a behind-goal camera looking along x toward midfield."""
    near = SETBACK_M
    far = SETBACK_M + pitch.length_m / 2  # its useful zone: the near half
    d = _bisector_ground_distance(height, near, far)
    x_cam = sign * (pitch.length_m / 2 + SETBACK_M)
    return np.array([x_cam - sign * d, 0.0, 0.0])


def architecture_a(pitch: PitchSpec, height_m: float = 12.0) -> RigConfig:
    """Single very-wide-angle 4K covering the whole pitch (panoramic-class)."""
    pos = np.array([0.0, _mast_y(pitch), height_m])
    cam = CameraSpec(
        name="A-wide",
        width_px=UHD[0],
        height_px=UHD[1],
        hfov_deg=130.0,  # near corners need ~±65 deg from a sideline mast
        position=pos,
        aim_at=_sideline_aim(pitch, height_m, 0.0),
        k1=-0.03,
    )
    return RigConfig("A", "single elevated wide-angle 4K", [cam])


def architecture_b(pitch: PitchSpec, height_m: float = 15.0) -> RigConfig:
    """Two 4K on one midline mast, one per half, center overlap."""
    pos = np.array([0.0, _mast_y(pitch), height_m])
    quarter = pitch.length_m / 4
    cams = [
        CameraSpec(
            name=f"B-{side}",
            width_px=UHD[0],
            height_px=UHD[1],
            hfov_deg=68.0,
            position=pos,
            aim_at=_sideline_aim(pitch, height_m, sign * quarter),
            k1=-0.05,
        )
        for side, sign in (("left", -1.0), ("right", 1.0))
    ]
    return RigConfig("B", "two 4K, midline mast, halves + overlap", cams)


def architecture_c(pitch: PitchSpec, height_m: float = 15.0) -> RigConfig:
    """Four 4K on one midline mast covering quarters (C-geometry,
    B-software: fused in pitch coordinates, never pixel-stitched)."""
    pos = np.array([0.0, _mast_y(pitch), height_m])
    eighth = pitch.length_m / 8
    aims_x = [(-3 * eighth), (-eighth), eighth, (3 * eighth)]
    cams = [
        CameraSpec(
            name=f"C-{i}",
            width_px=UHD[0],
            height_px=UHD[1],
            hfov_deg=45.0,
            position=pos,
            aim_at=_sideline_aim(pitch, height_m, ax),
            k1=-0.02,
        )
        for i, ax in enumerate(aims_x)
    ]
    return RigConfig("C", "four 4K, midline mast, quarters", cams)


def architecture_d(pitch: PitchSpec, height_m: float = 15.0) -> RigConfig:
    """Distributed: both sidelines + both goal ends (TRACAB-Gen5-shaped)."""
    mast_y = _mast_y(pitch)
    sideline = [
        CameraSpec(
            name="D-side-near",
            width_px=UHD[0],
            height_px=UHD[1],
            hfov_deg=130.0,
            position=np.array([0.0, mast_y, height_m]),
            aim_at=_sideline_aim(pitch, height_m, 0.0),
            k1=-0.03,
        ),
        CameraSpec(
            name="D-side-far",
            width_px=UHD[0],
            height_px=UHD[1],
            hfov_deg=130.0,
            position=np.array([0.0, -mast_y, height_m]),
            aim_at=np.array([0.0, -_sideline_aim(pitch, height_m, 0.0)[1], 0.0]),
            k1=-0.03,
        ),
    ]
    ends = [
        CameraSpec(
            name=f"D-end-{'left' if sign < 0 else 'right'}",
            width_px=UHD[0],
            height_px=UHD[1],
            hfov_deg=110.0,
            position=np.array(
                [sign * (pitch.length_m / 2 + SETBACK_M), 0.0, height_m]
            ),
            aim_at=_endline_aim(pitch, height_m, sign),
            k1=-0.03,
        )
        for sign in (-1.0, 1.0)
    ]
    return RigConfig(
        "D",
        "distributed multi-camera, 2 sidelines + 2 ends",
        sideline + ends,
        multi_viewpoint=True,
    )


def architecture_dn(pitch: PitchSpec, height_m: float = 15.0) -> RigConfig:
    """D with narrower lenses: B-style 68-degree pairs on BOTH sideline masts
    plus the two end cameras (6 cameras) — multi-viewpoint occlusion breaking
    at B/C-class pixel density (Gate 0A instructions section 19 variant)."""
    quarter = pitch.length_m / 4
    mast_y = _mast_y(pitch)
    near_aims = [_sideline_aim(pitch, height_m, s * quarter) for s in (-1.0, 1.0)]
    cams = [
        CameraSpec(
            name=f"Dn-near-{i}",
            width_px=UHD[0],
            height_px=UHD[1],
            hfov_deg=68.0,
            position=np.array([0.0, mast_y, height_m]),
            aim_at=aim,
            k1=-0.05,
        )
        for i, aim in enumerate(near_aims)
    ]
    cams += [
        CameraSpec(
            name=f"Dn-far-{i}",
            width_px=UHD[0],
            height_px=UHD[1],
            hfov_deg=68.0,
            position=np.array([0.0, -mast_y, height_m]),
            aim_at=np.array([aim[0], -aim[1], 0.0]),
            k1=-0.05,
        )
        for i, aim in enumerate(near_aims)
    ]
    cams += [
        CameraSpec(
            name=f"Dn-end-{'left' if sign < 0 else 'right'}",
            width_px=UHD[0],
            height_px=UHD[1],
            hfov_deg=110.0,
            position=np.array(
                [sign * (pitch.length_m / 2 + SETBACK_M), 0.0, height_m]
            ),
            aim_at=_endline_aim(pitch, height_m, sign),
            k1=-0.03,
        )
        for sign in (-1.0, 1.0)
    ]
    return RigConfig(
        "Dn",
        "distributed narrow-lens: 2x2 sideline 68deg + 2 ends",
        cams,
        multi_viewpoint=True,
    )


PRESETS = {
    "A": architecture_a,
    "B": architecture_b,
    "C": architecture_c,
    "D": architecture_d,
    "Dn": architecture_dn,
}
