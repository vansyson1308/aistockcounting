import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "license_gate", REPO / "scripts" / "license_gate.py"
)
gate = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(gate)


def test_license_gate_passes() -> None:
    assert gate.main() == 0


def test_runtime_manifests_have_no_banned_packages() -> None:
    for rel in gate.RUNTIME_MANIFESTS:
        path = REPO / rel
        assert gate.scan_manifest(path, REPO) == [], rel
        assert not any(r == rel for r, _ in gate.GRANDFATHERED)


def test_runtime_has_no_ultralytics_import() -> None:
    app = REPO / "backend" / "app"
    offenders = [
        p for p in app.rglob("*.py") if "ultralytics" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []
