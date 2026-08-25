"""Pinhole camera + radial distortion projection over a football pitch.

World frame: origin at pitch center, x along pitch length (+x toward the
"right" goal), y along pitch width (+y toward the far touchline), z up.
Image frame: u right, v down, origin at the principal point offsetted to the
top-left corner (u in [0, W), v in [0, H)).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

UP_WORLD = np.array([0.0, 0.0, 1.0])


@dataclass
class PitchSpec:
    length_m: float = 105.0
    width_m: float = 68.0


@dataclass
class CameraSpec:
    """One physical camera: sensor, lens, mount pose."""

    name: str
    width_px: int
    height_px: int
    hfov_deg: float  # horizontal field of view (after lens choice)
    position: np.ndarray  # (3,) world meters
    aim_at: np.ndarray  # (3,) world point the optical axis passes through
    k1: float = 0.0  # radial distortion (Brown-Conrady, normalized coords)
    k2: float = 0.0

    _R: np.ndarray = field(init=False, repr=False)
    _f_px: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.position = np.asarray(self.position, dtype=np.float64)
        self.aim_at = np.asarray(self.aim_at, dtype=np.float64)
        forward = self.aim_at - self.position
        norm = np.linalg.norm(forward)
        if norm == 0:
            raise ValueError("aim_at must differ from position")
        forward = forward / norm
        if abs(float(np.dot(forward, UP_WORLD))) > 0.999:
            raise ValueError("optical axis may not be vertical")
        right = np.cross(forward, UP_WORLD)
        right = right / np.linalg.norm(right)
        down = np.cross(forward, right)
        self._R = np.stack([right, down, forward])  # world -> camera rows
        self._f_px = (self.width_px / 2.0) / np.tan(np.radians(self.hfov_deg) / 2.0)

    # ------------------------------------------------------------ projection

    def project(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Project (N,3) world points → ((N,2) pixels, (N,) visibility)."""
        pts = np.atleast_2d(np.asarray(points, dtype=np.float64))
        cam = (pts - self.position) @ self._R.T
        z = cam[:, 2]
        in_front = z > 1e-6
        zsafe = np.where(in_front, z, 1.0)
        xn = cam[:, 0] / zsafe
        yn = cam[:, 1] / zsafe
        r2 = xn * xn + yn * yn
        factor = 1.0 + self.k1 * r2 + self.k2 * r2 * r2
        u = self.width_px / 2.0 + self._f_px * xn * factor
        v = self.height_px / 2.0 + self._f_px * yn * factor
        pix = np.stack([u, v], axis=1)
        visible = (
            in_front
            & (u >= 0)
            & (u < self.width_px)
            & (v >= 0)
            & (v < self.height_px)
        )
        return pix, visible

    # ------------------------------------------------------- derived fields

    def vertical_px_per_m(self, ground_points: np.ndarray) -> np.ndarray:
        """Pixels per vertical meter at each ground point (player-height axis).

        Computed as the pixel distance between a ground point and the same
        point raised by 1 m — i.e. exactly what a 1 m tall object spans.
        NaN where either endpoint is invisible.
        """
        pts = np.atleast_2d(ground_points)
        top = pts + np.array([0.0, 0.0, 1.0])
        p0, v0 = self.project(pts)
        p1, v1 = self.project(top)
        d = np.linalg.norm(p1 - p0, axis=1)
        return np.where(v0 & v1, d, np.nan)

    def horizontal_px_per_m(self, ground_points: np.ndarray) -> np.ndarray:
        """Pixels per meter of ground displacement (max over x/y directions)."""
        pts = np.atleast_2d(ground_points)
        out = np.full(len(pts), np.nan)
        p0, v0 = self.project(pts)
        for axis in (np.array([1.0, 0, 0]), np.array([0, 1.0, 0])):
            p1, v1 = self.project(pts + axis)
            d = np.linalg.norm(p1 - p0, axis=1)
            cand = np.where(v0 & v1, d, np.nan)
            out = np.fmax(out, cand)
        return out

    def elevation_deg(self, ground_points: np.ndarray) -> np.ndarray:
        """Elevation angle (degrees) of the camera seen from each ground point."""
        pts = np.atleast_2d(ground_points)
        delta = self.position - pts
        horiz = np.linalg.norm(delta[:, :2], axis=1)
        return np.degrees(np.arctan2(delta[:, 2], np.maximum(horiz, 1e-9)))

    def distance_m(self, ground_points: np.ndarray) -> np.ndarray:
        pts = np.atleast_2d(ground_points)
        return np.linalg.norm(pts - self.position, axis=1)


def pitch_grid(pitch: PitchSpec, step_m: float = 1.0) -> np.ndarray:
    """(N,3) ground points covering the pitch at `step_m` spacing."""
    xs = np.arange(-pitch.length_m / 2, pitch.length_m / 2 + 1e-9, step_m)
    ys = np.arange(-pitch.width_m / 2, pitch.width_m / 2 + 1e-9, step_m)
    gx, gy = np.meshgrid(xs, ys)
    pts = np.stack([gx.ravel(), gy.ravel(), np.zeros(gx.size)], axis=1)
    return pts
