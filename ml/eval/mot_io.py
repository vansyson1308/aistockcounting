"""MOTChallenge-format IO.

Row format: frame, id, bb_left, bb_top, bb_width, bb_height, conf, x, y, z
(1-based frames; -1 for unused world coordinates).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def read_mot(path: str | Path) -> dict[int, list[tuple[int, np.ndarray, float]]]:
    """Read a MOT file → {frame: [(track_id, xyxy, conf), ...]}."""
    frames: dict[int, list[tuple[int, np.ndarray, float]]] = {}
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(",")
        frame = int(float(parts[0]))
        tid = int(float(parts[1]))
        x, y, w, h = (float(v) for v in parts[2:6])
        conf = float(parts[6]) if len(parts) > 6 else 1.0
        frames.setdefault(frame, []).append(
            (tid, np.array([x, y, x + w, y + h]), conf)
        )
    return frames


def write_mot(
    path: str | Path, rows: list[tuple[int, int, float, float, float, float, float]]
) -> None:
    """Write rows of (frame, id, x, y, w, h, conf)."""
    lines = [
        f"{frame},{tid},{x:.2f},{y:.2f},{w:.2f},{h:.2f},{conf:.4f},-1,-1,-1"
        for frame, tid, x, y, w, h, conf in rows
    ]
    Path(path).write_text("\n".join(lines) + ("\n" if lines else ""))
