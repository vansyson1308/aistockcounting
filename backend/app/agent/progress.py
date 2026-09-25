"""In-process registry of running agent runs, for the live timeline.

The API runs a single uvicorn worker (CV work runs in threads; OpenCV releases
the GIL), so an in-memory registry is enough. Finished runs are also persisted
to ``agent_steps``, which is the source of truth.
"""

from __future__ import annotations

import threading
import time
from typing import Any

_LOCK = threading.Lock()
_RUNS: dict[str, dict[str, Any]] = {}
TTL_S = 600


def start(scan_id: str, run_id: str) -> None:
    with _LOCK:
        _gc()
        _RUNS[scan_id] = {
            "run_id": run_id,
            "running": True,
            "steps": [],
            "t": time.time(),
        }


def add_step(scan_id: str, step: dict[str, Any]) -> None:
    with _LOCK:
        if scan_id in _RUNS:
            _RUNS[scan_id]["steps"].append(step)


def finish(scan_id: str) -> None:
    with _LOCK:
        if scan_id in _RUNS:
            _RUNS[scan_id]["running"] = False


def get(scan_id: str) -> dict[str, Any] | None:
    with _LOCK:
        run = _RUNS.get(scan_id)
        return None if run is None else {**run, "steps": list(run["steps"])}


def _gc() -> None:
    now = time.time()
    for k in [k for k, v in _RUNS.items() if now - v["t"] > TTL_S]:
        del _RUNS[k]
