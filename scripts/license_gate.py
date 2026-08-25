#!/usr/bin/env python3
"""Dependency license gate (docs/dependency-policy.md).

Scans dependency manifests for packages banned from the product core
(AGPL/GPL/HL3/non-commercial/no-license components). Fails CI on any banned
name that is not covered by the explicit, shrinking grandfather list.

Stdlib-only and deterministic: it matches manifest entries against a curated
denylist by name; it does not query package indexes.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Banned package/distribution names (normalized), with the reason.
# Policy: docs/dependency-policy.md rule 2. Names only shrink from
# "banned" to "allowed" via a Recorded decision in that document.
BANNED: dict[str, str] = {
    "ultralytics": "AGPL-3.0 (replace with Apache-2.0 detector stack; see policy)",
    "yolov5": "AGPL-3.0 (Ultralytics)",
    "boxmot": "AGPL-3.0 (mikel-brostrom/boxmot)",
    "yolo-tracking": "AGPL-3.0 (former name of boxmot)",
    "strongsort": "GPL-3.0 (reimplement AFLink/GSI from the paper instead)",
    "prtreid": "Hippocratic License 3.0 (paper-reference only)",
    "sn-gamestate": "GPL-3.0 (architecture reference only)",
    "sn-calibration": "no license file (all rights reserved)",
    "pnlcalib": "GPL-2.0 (reimplement from the CVIU paper instead)",
    "paddlex": "review required before use",
}

# (manifest path, banned name) pairs tolerated as legacy exceptions.
# This list only shrinks; it is deleted entirely at Phase 0b.
GRANDFATHERED: set[tuple[str, str]] = {
    ("backend/requirements.txt", "ultralytics"),
    ("training/requirements-train.txt", "ultralytics"),
}

MANIFEST_GLOBS = [
    "requirements*.txt",
    "*/requirements*.txt",
    "*/*/requirements*.txt",
    "pyproject.toml",
    "*/pyproject.toml",
    "package.json",
    "*/package.json",
]

_REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _normalize(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def names_from_requirements(text: str) -> list[str]:
    names: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "--")):
            # Also catch VCS/URL requirements by scanning the whole line below.
            pass
        m = _REQ_NAME_RE.match(line)
        if m:
            names.append(_normalize(m.group(1)))
        # VCS/URL requirements (e.g. git+https://github.com/org/banned.git)
        for banned in BANNED:
            if banned in _normalize(line) and (not m or _normalize(m.group(1)) != banned):
                names.append(banned)
    return names


def names_from_pyproject(text: str) -> list[str]:
    # Minimal parse: collect quoted requirement strings from dependency arrays.
    names: list[str] = []
    for m in re.finditer(r'"([^"\n]+)"', text):
        candidate = m.group(1)
        req = _REQ_NAME_RE.match(candidate)
        if req:
            names.append(_normalize(req.group(1)))
    return names


def names_from_package_json(text: str) -> list[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    names: list[str] = []
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        names.extend(_normalize(n) for n in data.get(key, {}))
    return names


def scan_manifest(path: Path, repo_root: Path) -> list[tuple[str, str, str]]:
    """Return violations as (relative manifest path, package, reason)."""
    rel = path.relative_to(repo_root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.name == "package.json":
        names = names_from_package_json(text)
    elif path.name == "pyproject.toml":
        names = names_from_pyproject(text)
    else:
        names = names_from_requirements(text)
    violations = []
    for name in names:
        if name in BANNED and (rel, name) not in GRANDFATHERED:
            violations.append((rel, name, BANNED[name]))
    return violations


def find_manifests(repo_root: Path) -> list[Path]:
    found: set[Path] = set()
    for pattern in MANIFEST_GLOBS:
        for p in repo_root.glob(pattern):
            if "node_modules" in p.parts or ".git" in p.parts:
                continue
            if p.is_file():
                found.add(p)
    return sorted(found)


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    manifests = find_manifests(repo_root)
    all_violations: list[tuple[str, str, str]] = []
    for manifest in manifests:
        all_violations.extend(scan_manifest(manifest, repo_root))

    grandfathered_hits = []
    for rel, name in sorted(GRANDFATHERED):
        if (repo_root / rel).is_file():
            grandfathered_hits.append((rel, name))

    print(f"license gate: scanned {len(manifests)} manifest(s)")
    for rel, name in grandfathered_hits:
        print(f"  legacy exception (expires Phase 0b): {rel}: {name}")
    if all_violations:
        print("license gate: FAIL — banned dependencies found:", file=sys.stderr)
        for rel, name, reason in all_violations:
            print(f"  {rel}: {name} — {reason}", file=sys.stderr)
        print("policy: docs/dependency-policy.md", file=sys.stderr)
        return 1
    print("license gate: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
