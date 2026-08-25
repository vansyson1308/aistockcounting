import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "license_gate", REPO_ROOT / "scripts" / "license_gate.py"
)
license_gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_spec and license_gate)


def test_requirements_parser_catches_pins_and_vcs_urls():
    text = (
        "numpy>=1.26\n"
        "ultralytics==8.3.0  # banned\n"
        "some-pkg @ git+https://github.com/mikel-brostrom/boxmot.git\n"
    )
    names = license_gate.names_from_requirements(text)
    assert "ultralytics" in names
    assert "boxmot" in names
    assert "numpy" in names


def test_scan_manifest_flags_banned(tmp_path):
    manifest = tmp_path / "ml" / "requirements.txt"
    manifest.parent.mkdir()
    manifest.write_text("numpy\nultralytics==8.3.0\n")
    violations = license_gate.scan_manifest(manifest, tmp_path)
    assert [(v[0], v[1]) for v in violations] == [
        ("ml/requirements.txt", "ultralytics")
    ]


def test_grandfathered_manifest_not_flagged(tmp_path):
    manifest = tmp_path / "backend" / "requirements.txt"
    manifest.parent.mkdir()
    manifest.write_text("ultralytics==8.3.0\n")
    assert license_gate.scan_manifest(manifest, tmp_path) == []


def test_package_json_dependencies_scanned(tmp_path):
    manifest = tmp_path / "package.json"
    manifest.write_text('{"dependencies": {"react": "18.0.0"}}')
    assert license_gate.scan_manifest(manifest, tmp_path) == []


def test_gate_passes_on_this_repository():
    manifests = license_gate.find_manifests(REPO_ROOT)
    violations = []
    for m in manifests:
        violations.extend(license_gate.scan_manifest(m, REPO_ROOT))
    assert violations == []
