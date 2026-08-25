"""Constant-velocity Kalman filter over box center; size tracked by EMA.

Clean-room implementation of the standard CV filter used by SORT-family
trackers. State: [cx, cy, vx, vy]; measurements: [cx, cy]. Width/height are
smoothed exponentially outside the filter (adequate for the Phase 0a seed;
a full box-state filter is a later refinement).
"""

from __future__ import annotations

import numpy as np


class CenterKalman:
    def __init__(
        self,
        cx: float,
        cy: float,
        process_var: float = 1.0,
        measurement_var: float = 1.0,
    ) -> None:
        self.x = np.array([cx, cy, 0.0, 0.0], dtype=np.float64)
        self.P = np.diag([10.0, 10.0, 100.0, 100.0])
        self.q = float(process_var)
        self.r = float(measurement_var)
        self._F = np.eye(4)
        self._F[0, 2] = 1.0
        self._F[1, 3] = 1.0
        self._H = np.zeros((2, 4))
        self._H[0, 0] = 1.0
        self._H[1, 1] = 1.0

    def predict(self) -> np.ndarray:
        self.x = self._F @ self.x
        # White-accel process noise, dt = 1 frame.
        G = np.array([[0.5, 0.0], [0.0, 0.5], [1.0, 0.0], [0.0, 1.0]])
        Q = self.q * (G @ G.T)
        self.P = self._F @ self.P @ self._F.T + Q
        return self.x[:2].copy()

    def update(self, cx: float, cy: float) -> None:
        z = np.array([cx, cy], dtype=np.float64)
        R = np.eye(2) * self.r
        y = z - self._H @ self.x
        S = self._H @ self.P @ self._H.T + R
        K = self.P @ self._H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(4) - K @ self._H) @ self.P

    @property
    def center(self) -> np.ndarray:
        return self.x[:2].copy()

    @property
    def velocity(self) -> np.ndarray:
        return self.x[2:].copy()
