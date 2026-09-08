"""Package the report tree (always) and push small reports to GitHub (optional).

GH_PAT is never required: without it the zip under the outputs directory is
the deliverable. With it, only files under reports/ smaller than `max_bytes`
are committed to the dedicated branch via the Git Data API in ONE commit
(never to main). Tokens are sent only in the Authorization header.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

from ml.gate0a.cloud.secrets import get_secret, redact

API = "https://api.github.com"


def zip_reports(out_root: Path) -> Path:
    rep = Path(out_root) / "reports"
    target = Path(out_root) / "gate0a_stage012_reports"
    archive = shutil.make_archive(str(target), "zip", root_dir=str(rep.parent), base_dir="reports")
    return Path(archive)


def collect_files(out_root: Path, max_bytes: int) -> tuple[list[tuple[str, Path]], list[str]]:
    rep = Path(out_root) / "reports"
    keep, skipped = [], []
    for p in sorted(rep.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(Path(out_root)).as_posix()
        if p.stat().st_size > max_bytes:
            skipped.append(rel)
            continue
        keep.append((rel, p))
    return keep, skipped


def _req(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "Content-Type": "application/json", "User-Agent": "gate0a-cloud-publish"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode() or "{}")


def push_reports(out_root: Path, repo: str, branch: str, token: str, max_bytes: int = 900_000,
                 message: str = "reports(gate0a-cloud): Stage 0+1+2 diagnostic artifacts") -> dict:
    if branch in ("main", "master"):
        raise PermissionError("refusing to push reports to the default branch")
    files, skipped = collect_files(out_root, max_bytes)
    if not files:
        return {"pushed": 0, "skipped": skipped, "reason": "no files"}
    ref = _req("GET", f"{API}/repos/{repo}/git/ref/heads/{branch}", token)
    head_sha = ref["object"]["sha"]
    head_commit = _req("GET", f"{API}/repos/{repo}/git/commits/{head_sha}", token)
    tree_entries = []
    for rel, p in files:
        blob = _req("POST", f"{API}/repos/{repo}/git/blobs", token,
                    {"content": base64.b64encode(p.read_bytes()).decode(), "encoding": "base64"})
        tree_entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    tree = _req("POST", f"{API}/repos/{repo}/git/trees", token,
                {"base_tree": head_commit["tree"]["sha"], "tree": tree_entries})
    commit = _req("POST", f"{API}/repos/{repo}/git/commits", token,
                  {"message": message, "tree": tree["sha"], "parents": [head_sha]})
    _req("PATCH", f"{API}/repos/{repo}/git/refs/heads/{branch}", token, {"sha": commit["sha"], "force": False})
    return {"pushed": len(files), "skipped": skipped, "commit": commit["sha"], "branch": branch}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("/kaggle/working/gate0a_outputs"))
    ap.add_argument("--repo", default="vansyson1308/aistockcounting")
    ap.add_argument("--branch", default="gate0a-cloud-stage12")
    args = ap.parse_args(argv)
    archive = zip_reports(args.out)
    print(f"reports archive: {archive} ({archive.stat().st_size / 2**20:.1f} MB) — download from the "
          f"notebook Output tab if no GitHub push happened")
    token = get_secret("GH_PAT")
    if not token:
        print("GH_PAT absent → skipping GitHub push (not a blocker)")
        return 0
    try:
        res = push_reports(args.out, args.repo, args.branch, token)
        print("GitHub push:", json.dumps({k: v for k, v in res.items() if k != "skipped"}),
              f"skipped(large)={len(res.get('skipped', []))}")
    except (urllib.error.HTTPError, urllib.error.URLError, PermissionError, KeyError) as exc:
        print("GitHub push failed (non-fatal):", redact(str(exc))[:300])
    return 0


if __name__ == "__main__":
    sys.exit(main())
