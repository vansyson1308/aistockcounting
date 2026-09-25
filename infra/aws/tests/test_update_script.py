"""Runs deploy/aws/update.sh against stub `aws` and `docker` commands.

Checks the host-side contract without an EC2 instance: the script refreshes
itself from SSM, assembles .env from app.env + secrets.env + image.env, syncs
the model from S3 (falling back to the classical detector) and runs compose.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

INFRA_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = INFRA_DIR.parents[1]
sys.path.insert(0, str(INFRA_DIR))

from trayagent_stack import strip_comment_lines  # noqa: E402

# The script exactly as CDK stores it in SSM (comment lines stripped).
UPDATE_SH = strip_comment_lines(
    (REPO_ROOT / "deploy" / "aws" / "update.sh").read_text()
)

AWS_STUB = r"""#!/bin/bash
# aws stub: SSM parameters and S3 objects are files under $STUB_ROOT.
echo "aws $*" >>"$STUB_ROOT/calls.log"
case "$1 $2" in
  "ssm get-parameter")
    while [[ $# -gt 0 ]]; do [[ "$1" == --name ]] && name="$2"; shift; done
    cat "$STUB_ROOT/ssm/${name##*/}" ;;
  "s3 cp")
    src="${@: -2:1}"; dest="${@: -1}"
    [[ -f "$STUB_ROOT/s3/${src#s3://*/}" ]] || exit 1
    cp "$STUB_ROOT/s3/${src#s3://*/}" "$dest" ;;
  "ecr get-login-password") echo stub-password ;;
  *) echo "unexpected aws call: $*" >&2; exit 99 ;;
esac
"""

DOCKER_STUB = r"""#!/bin/bash
[[ "$1" == login ]] && cat >/dev/null
echo "docker $*" >>"$STUB_ROOT/calls.log"
"""

APP_ENV = """AWS_REGION=ap-southeast-1
S3_BUCKET=evidence-bucket
LOG_GROUP=/trayagent/TrayAgent
ECR_REGISTRY=123456789012.dkr.ecr.ap-southeast-1.amazonaws.com
BACKEND_IMAGE=123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/trayagent-backend
FRONTEND_IMAGE=123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/trayagent-frontend
DETECTOR_BACKEND={detector}
MODEL_S3_KEY={model_key}
AGENT_PLANNER=deterministic
BEDROCK_MODEL_ID=
CORS_ORIGINS=https://d123.cloudfront.net
DEFAULT_TENANT_KEY=demo
"""


@pytest.fixture()
def host(tmp_path: Path) -> Path:
    if not shutil.which("flock"):
        pytest.skip("flock (util-linux) not available")
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    for name, body in (("aws", AWS_STUB), ("docker", DOCKER_STUB)):
        path = stub_bin / name
        path.write_text(body)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "ssm").mkdir()
    (tmp_path / "s3" / "models").mkdir(parents=True)
    (tmp_path / "ssm" / "update-sh").write_text(UPDATE_SH)
    (tmp_path / "ssm" / "compose").write_text("name: trayagent\n")
    (tmp_path / "ssm" / "nginx").write_text("events {}\n")

    opt = tmp_path / "opt"
    (opt / "models").mkdir(parents=True)
    (opt / "instance.env").write_text(
        "AWS_REGION=ap-southeast-1\nPARAM_PREFIX=/trayagent/TrayAgent\n"
    )
    (opt / "secrets.env").write_text("POSTGRES_PASSWORD=s3cret\n")
    # An older, still working version is installed; SSM holds the current one.
    (opt / "update.sh").write_text(
        UPDATE_SH.replace("TrayAgent is up", "OLD VERSION is up")
    )
    (opt / "update.sh").chmod(0o700)
    return tmp_path


def _run(
    host: Path, *args: str, detector: str = "classical", model_key: str = ""
) -> subprocess.CompletedProcess:
    (host / "ssm" / "app-env").write_text(
        APP_ENV.format(detector=detector, model_key=model_key)
    )
    env = {
        **os.environ,
        "PATH": f"{host / 'bin'}:{os.environ['PATH']}",
        "STUB_ROOT": str(host),
        "TRAYAGENT_DIR": str(host / "opt"),
    }
    return subprocess.run(
        ["bash", str(host / "opt" / "update.sh"), *args],
        env=env,
        capture_output=True,
        text=True,
    )


def _env_file(host: Path) -> dict[str, str]:
    lines = (host / "opt" / ".env").read_text().splitlines()
    return dict(line.split("=", 1) for line in lines if line)


def test_self_update_env_and_compose(host: Path) -> None:
    result = _run(host, "abc1234")
    assert result.returncode == 0, result.stderr
    # The old on-disk script was replaced by the SSM copy and re-executed.
    assert (host / "opt" / "update.sh").read_text() == UPDATE_SH
    assert "TrayAgent is up: IMAGE_TAG=abc1234" in result.stdout
    env = _env_file(host)
    assert env["IMAGE_TAG"] == "abc1234"
    assert env["POSTGRES_PASSWORD"] == "s3cret"
    assert env["DETECTOR_BACKEND"] == "classical"
    assert oct((host / "opt" / ".env").stat().st_mode & 0o777) == "0o600"
    assert (host / "opt" / "docker-compose.yml").read_text() == "name: trayagent\n"
    calls = (host / "calls.log").read_text()
    assert "docker login --username AWS --password-stdin 123456789012.dkr.ecr" in calls
    assert "docker compose pull" in calls
    assert "docker compose up -d --remove-orphans --wait" in calls

    # Without a tag argument the previous tag is kept.
    assert _run(host).returncode == 0
    assert _env_file(host)["IMAGE_TAG"] == "abc1234"


def test_rejects_bad_image_tag(host: Path) -> None:
    result = _run(host, "bad tag;rm -rf /")
    assert result.returncode == 2
    assert "bad image tag" in result.stderr


def test_model_sync_from_s3(host: Path) -> None:
    (host / "s3" / "models" / "trayagent_v1.onnx").write_bytes(b"onnx")
    (host / "s3" / "models" / "trayagent_v1.json").write_text(
        '{"input_size": [640, 640]}'
    )
    result = _run(host, detector="onnx", model_key="models/trayagent_v1.onnx")
    assert result.returncode == 0, result.stderr
    assert (host / "opt" / "models" / "trayagent_v1.onnx").read_bytes() == b"onnx"
    assert (host / "opt" / "models" / "trayagent_v1.json").exists()
    assert _env_file(host)["DETECTOR_BACKEND"] == "onnx"


def test_missing_model_falls_back_to_classical(host: Path) -> None:
    result = _run(host, detector="onnx", model_key="models/missing.onnx")
    assert result.returncode == 0, result.stderr
    assert "using the classical detector" in result.stderr
    assert _env_file(host)["DETECTOR_BACKEND"] == "classical"
