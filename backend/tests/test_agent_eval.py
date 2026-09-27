"""The Phase 7 evaluation script, exercised in its synthetic smoke mode only."""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "training" / "scripts" / "agent_eval.py"


def test_synthetic_smoke_is_stamped_and_complete(tmp_path: Path) -> None:
    out = tmp_path / "eval"
    r = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--synthetic-smoke",
            "--backend",
            "classical",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=600,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    text = (out / "RESULTS.md").read_text()
    assert "SYNTHETIC SMOKE TEST: NOT A RESULT" in text
    for needle in (
        "mAP@0.5",
        "Count MAE",
        "FALSE auto-accept",
        "latency p50 / p95",
        "Failure gallery",
    ):
        assert needle in text
    assert (out / "results.csv").exists() and (out / "summary.json").exists()


def test_synthetic_output_refused_under_reports(tmp_path: Path) -> None:
    r = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--synthetic-smoke",
            "--backend",
            "classical",
            "--out",
            str(tmp_path / "reports" / "agentic"),
        ],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
    )
    assert r.returncode != 0 and "must not go under reports" in r.stderr


def test_refuses_unfrozen_real_eval(tmp_path: Path) -> None:
    root = tmp_path / "vj"
    (root / "images" / "test").mkdir(parents=True)
    r = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(root),
            "--backend",
            "classical",
            "--out",
            str(tmp_path / "o"),
        ],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
    )
    assert r.returncode != 0 and "frozen test set check failed" in r.stderr
