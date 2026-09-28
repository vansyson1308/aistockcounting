"""Machine-readable run manifest (§19) — makes any result rerunnable.

Everything is redacted through `secrets.redact_obj` before serialization.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from ml.gate0a.cloud import CLOUD_LAYER_VERSION
from ml.gate0a.cloud.secrets import redact_obj


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def file_sha256(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_sha(repo_root: Path | None = None) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root) if repo_root else None,
            capture_output=True,
            text=True,
            timeout=20,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def package_versions(names: tuple[str, ...]) -> dict[str, str | None]:
    from importlib.metadata import PackageNotFoundError, version

    out: dict[str, str | None] = {}
    for n in names:
        try:
            out[n] = version(n)
        except PackageNotFoundError:
            out[n] = None
    return out


def gpu_info() -> dict:
    info: dict = {"cuda_available": False}
    try:
        import torch

        info["torch"] = torch.__version__
        info["cuda_version"] = torch.version.cuda
        info["cuda_available"] = bool(torch.cuda.is_available())
        if info["cuda_available"]:
            props = torch.cuda.get_device_properties(0)
            info["gpu_name"] = props.name
            info["vram_gb"] = round(props.total_memory / 2**30, 2)
            info["gpu_count"] = torch.cuda.device_count()
    except Exception as exc:  # pragma: no cover - environment dependent
        info["error"] = str(exc)
    return info


def build_manifest(
    *,
    repo_root: Path,
    contract_sha256: str,
    config: dict,
    dataset: dict,
    windows_sha256: str | None,
    detector: dict,
    reid: dict,
    tracker_config: dict,
    offline_config: dict,
    seeds: dict,
    started_at: str,
    finished_at: str | None,
    extra: dict | None = None,
) -> dict:
    manifest = {
        "cloud_layer_version": CLOUD_LAYER_VERSION,
        "repo_sha": git_sha(repo_root),
        "diagnostic_contract_sha256": contract_sha256,
        "dataset": dataset,
        "clip_manifest_sha256": windows_sha256,
        "detector": detector,
        "reid": reid,
        "tracker_config": tracker_config,
        "offline_config": offline_config,
        "seeds": seeds,
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            **gpu_info(),
            "packages": package_versions(
                ("torch", "torchvision", "transformers", "huggingface_hub",
                 "opencv-python-headless", "opencv-python", "numpy", "scipy",
                 "trackeval")
            ),
        },
        "config": config,
        "started_at": started_at,
        "finished_at": finished_at,
    }
    if extra:
        manifest["extra"] = extra
    return redact_obj(manifest)


def write_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact_obj(manifest), indent=2, default=str) + "\n")
