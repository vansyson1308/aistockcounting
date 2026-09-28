"""Manifest-hashed caching for expensive artifacts (resumability, §20).

An expensive step writes its outputs plus `<name>.cache.json` holding the
sha256 of its full input specification. On rerun the spec is recomputed:
identical → `SKIP — CACHE VALID`; different or missing → `CACHE INVALID —
RECOMPUTE`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SKIP = "SKIP — CACHE VALID"
RECOMPUTE = "CACHE INVALID — RECOMPUTE"


def spec_hash(spec: dict) -> str:
    blob = json.dumps(spec, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def cache_path(out_dir: Path, name: str) -> Path:
    return Path(out_dir) / f"{name}.cache.json"


def check(out_dir: Path, name: str, spec: dict, required: list[Path]) -> tuple[str, str]:
    """Return (status, spec_hash). Valid only if every required file exists."""
    h = spec_hash(spec)
    p = cache_path(out_dir, name)
    if not p.exists():
        return RECOMPUTE, h
    try:
        rec = json.loads(p.read_text())
    except json.JSONDecodeError:
        return RECOMPUTE, h
    if rec.get("spec_sha256") != h:
        return RECOMPUTE, h
    if not all(Path(f).exists() for f in required):
        return RECOMPUTE, h
    return SKIP, h


def commit(out_dir: Path, name: str, spec: dict, outputs: list[Path]) -> str:
    h = spec_hash(spec)
    rec = {
        "name": name,
        "spec_sha256": h,
        "spec": spec,
        "outputs": [str(o) for o in outputs],
    }
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    cache_path(out_dir, name).write_text(json.dumps(rec, indent=2, default=str) + "\n")
    return h
