#!/usr/bin/env python3
"""Gate 0A cloud Stage 0+1+2 — plain-script twin of the Kaggle notebook.

Runs anywhere with a CUDA GPU + internet (Kaggle, HF Jobs, a CUDA box):

    python gate0a_stage012_kaggle.py

Environment (all optional except HF_TOKEN):
    HF_TOKEN   read token of the HF account with SoccerTrack-v2 access
    GH_PAT     fine-grained token for pushing the small report tree
    GATE0A_REPO_URL / GATE0A_BRANCH / GATE0A_SHA / GATE0A_OUT / GATE0A_SCRATCH

DIAGNOSTIC — NOT OFFICIAL GATE 0A VERDICT · TEST SET UNTOUCHED
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_URL = os.environ.get("GATE0A_REPO_URL", "https://github.com/vansyson1308/aistockcounting")
BRANCH = os.environ.get("GATE0A_BRANCH", "gate0a-cloud-stage12")
SHA = os.environ.get("GATE0A_SHA", "")  # empty → branch head
OUT = Path(os.environ.get("GATE0A_OUT", "/kaggle/working/gate0a_outputs"))
SCRATCH = Path(os.environ.get("GATE0A_SCRATCH", "/kaggle/tmp/gate0a_scratch"))
REPO_DIR = Path(os.environ.get("GATE0A_REPO_DIR", "/kaggle/working/repo"))


def sh(cmd: list[str], cwd: Path | None = None, check: bool = True) -> int:
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=check).returncode


def load_kaggle_secrets() -> None:
    try:
        from kaggle_secrets import UserSecretsClient  # type: ignore
    except Exception:
        return
    client = UserSecretsClient()
    for name in ("HF_TOKEN", "GH_PAT"):
        if os.environ.get(name):
            continue
        try:
            value = client.get_secret(name)
            if value:
                os.environ[name] = value.strip()
        except Exception:
            pass


def preflight() -> None:
    print(f"python {sys.version.split()[0]}")
    if shutil.which("nvidia-smi"):
        sh(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv"], check=False)
    for p in (OUT.parent, SCRATCH.parent):
        if p.exists():
            u = shutil.disk_usage(p)
            print(f"disk {p}: free {u.free / 2**30:.1f} GiB of {u.total / 2**30:.1f} GiB")
    load_kaggle_secrets()
    print("secrets present:", {n: bool(os.environ.get(n)) for n in ("HF_TOKEN", "GH_PAT")})


def checkout() -> None:
    if not (REPO_DIR / ".git").exists():
        sh(["git", "clone", "--branch", BRANCH, "--single-branch", REPO_URL, str(REPO_DIR)])
    else:
        sh(["git", "-C", str(REPO_DIR), "fetch", "origin", BRANCH], check=False)
        sh(["git", "-C", str(REPO_DIR), "checkout", BRANCH], check=False)
        sh(["git", "-C", str(REPO_DIR), "pull", "--ff-only", "origin", BRANCH], check=False)
    if SHA:
        sh(["git", "-C", str(REPO_DIR), "checkout", SHA])
    sh(["git", "-C", str(REPO_DIR), "rev-parse", "HEAD"])
    sh([sys.executable, "-m", "pip", "install", "-q", "-r", "ml/gate0a/cloud/requirements-cloud.txt"],
       cwd=REPO_DIR)


def run_stages() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    return sh([sys.executable, "-m", "ml.gate0a.cloud.run_stage", "--stage", "all", "--out", str(OUT),
               "--scratch", str(SCRATCH)], cwd=REPO_DIR, check=False)


def publish() -> None:
    sh([sys.executable, "-m", "ml.gate0a.cloud.publish", "--out", str(OUT), "--branch", BRANCH],
       cwd=REPO_DIR, check=False)
    rep = OUT / "reports" / "gate0a" / "cloud" / "stage012"
    for name in ("maturity.json", "executive_report.md", "owner_action_required.md"):
        p = rep / name
        if p.exists():
            print(f"\n===== {name} =====\n{p.read_text()[:6000]}")


if __name__ == "__main__":
    preflight()
    checkout()
    code = run_stages()
    publish()
    if code == 3:
        print("\nCLOUD RUN PACKAGE: READY — waiting on owner UI authorization (see above).")
    sys.exit(0 if code in (0, 3) else code)
