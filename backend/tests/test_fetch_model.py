import hashlib
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "fetch_model.sh"


def _run(tmp: Path, src: Path, env_extra: dict | None = None):
    env = {
        "PATH": "/usr/bin:/bin",
        "MODEL_DIR": str(tmp / "models"),
        "MODEL_SOURCE": str(src),
    }
    env.update(env_extra or {})
    return subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True
    )


def test_fetch_verifies_sha256(tmp_path: Path) -> None:
    src = tmp_path / "w.onnx"
    src.write_bytes(b"onnx-bytes")
    (tmp_path / "models").mkdir()
    digest = hashlib.sha256(b"onnx-bytes").hexdigest()
    (tmp_path / "models" / "trayagent_v1.sha256").write_text(
        f"{digest}  trayagent_v1.onnx\n"
    )
    r = _run(tmp_path, src)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "models" / "trayagent_v1.onnx").read_bytes() == b"onnx-bytes"


def test_fetch_rejects_mismatch_and_leaves_nothing(tmp_path: Path) -> None:
    src = tmp_path / "w.onnx"
    src.write_bytes(b"tampered")
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "trayagent_v1.sha256").write_text(
        "0" * 64 + "  trayagent_v1.onnx\n"
    )
    r = _run(tmp_path, src)
    assert r.returncode == 1 and "mismatch" in r.stderr
    assert not (tmp_path / "models" / "trayagent_v1.onnx").exists()
    assert list((tmp_path / "models").glob(".trayagent_v1.*")) == []


def test_fetch_requires_committed_checksum(tmp_path: Path) -> None:
    src = tmp_path / "w.onnx"
    src.write_bytes(b"x")
    r = _run(tmp_path, src)
    assert r.returncode == 2 and "unverified" in r.stderr
