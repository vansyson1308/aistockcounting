import json

from ml.gate0a.cloud import secrets
from ml.gate0a.cloud.artifact_manifest import build_manifest

# Token-shaped fixtures are assembled at runtime so no credential-like literal
# ever exists in the source tree (keeps secret scanners quiet).
FAKE_HF = "hf_" + "A" * 30
FAKE_GHP = "ghp_" + "b" * 30
FAKE_PAT = "github_pat_" + "1" * 30


def test_redaction_masks_tokens(monkeypatch):
    txt = f"Authorization: Bearer {FAKE_HF} and {FAKE_GHP}"
    out = secrets.redact(txt)
    assert FAKE_HF[:8] not in out and FAKE_GHP[:8] not in out and "<REDACTED>" in out
    nested = secrets.redact_obj({"a": [FAKE_PAT], "b": {"token": "x" * 12}})
    assert FAKE_PAT[:14] not in json.dumps(nested)
    monkeypatch.setenv("HF_TOKEN", FAKE_HF)
    monkeypatch.delenv("GH_PAT", raising=False)
    assert secrets.describe_presence() == {"HF_TOKEN": True, "GH_PAT": False}


def test_manifest_fields_and_no_secret_leak(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", FAKE_HF)
    m = build_manifest(
        repo_root=tmp_path, contract_sha256="c" * 64, config={"note": f"token={FAKE_HF}"},
        dataset={"repo_id": "x/y", "revision": "r"}, windows_sha256="w" * 64,
        detector={"hf_id": "d", "weights_sha256": "s"}, reid={"name": "e"},
        tracker_config={"ambiguity_margin": 0.05}, offline_config={"merge_max_cost": 0.35},
        seeds={"global": 0}, started_at="t0", finished_at="t1",
    )
    for k in ("cloud_layer_version", "diagnostic_contract_sha256", "dataset", "clip_manifest_sha256",
              "detector", "reid", "tracker_config", "offline_config", "seeds", "runtime",
              "started_at", "finished_at"):
        assert k in m
    assert FAKE_HF[:8] not in json.dumps(m)
    assert "python" in m["runtime"] and "packages" in m["runtime"]
