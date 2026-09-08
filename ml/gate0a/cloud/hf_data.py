"""SoccerTrack-v2 selective access via the Hugging Face Hub (§9.1-9.2).

Nothing about the dataset layout is assumed: the live repository tree is
listed (with sizes and LFS hashes), the files for ONE match/half are located
by tolerant matching, and only those exact paths are downloaded. TEST match
ids are refused at every layer.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

_MATCH_ID_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
GT_NAME = "gt.txt"


@dataclass
class TreeEntry:
    path: str
    size: int
    lfs_sha256: str | None = None

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    @property
    def top(self) -> str:
        return self.path.split("/", 1)[0] if "/" in self.path else ""


def entries_from_tree(items) -> list[TreeEntry]:
    """Normalize `HfApi.list_repo_tree(..., expand=True)` items (or dicts)."""
    out: list[TreeEntry] = []
    for it in items:
        if isinstance(it, dict):
            path, size, lfs = it.get("path"), it.get("size"), it.get("lfs")
            typ = it.get("type", "file")
        else:
            path = getattr(it, "path", None)
            size = getattr(it, "size", None)
            lfs = getattr(it, "lfs", None)
            typ = "directory" if type(it).__name__ == "RepoFolder" else "file"
        if not path or typ == "directory":
            continue
        sha = None
        if lfs is not None:
            sha = lfs.get("sha256") if isinstance(lfs, dict) else getattr(lfs, "sha256", None)
        out.append(TreeEntry(path=str(path), size=int(size or 0), lfs_sha256=sha))
    return sorted(out, key=lambda e: e.path)


def match_ids_in_path(path: str) -> set[str]:
    return set(_MATCH_ID_RE.findall(path))


def assert_not_forbidden(paths: list[str], forbidden: list[str]) -> None:
    hits = sorted({m for p in paths for m in match_ids_in_path(p) if m in set(forbidden)})
    if hits:
        raise PermissionError(
            f"TEST match ids {hits} appear in a download/inspection plan — refused"
        )


def files_for_match(entries: list[TreeEntry], match_id: str) -> list[TreeEntry]:
    return [e for e in entries if match_id in match_ids_in_path(e.path)]


def _has_half_token(path: str, tokens: list[str]) -> bool:
    low = path.lower()
    return any(t.lower() in low for t in tokens)


def find_gt(entries: list[TreeEntry], match_id: str, half_tokens: list[str]) -> dict | None:
    cands = [e for e in files_for_match(entries, match_id) if e.name == GT_NAME]
    if not cands:
        return None
    half = [e for e in cands if _has_half_token(e.path, half_tokens)]
    if half:
        return {"path": half[0].path, "size": half[0].size, "scope": "per_half"}
    # Per-match GT keyed by <match_id> only (SoccerTrack v2 format-mot.md).
    plain = [e for e in cands if not any(
        t in e.path.lower() for t in ("2nd", "second", "half2", "half_2", "h2")
    )]
    e = (plain or cands)[0]
    return {"path": e.path, "size": e.size, "scope": "per_match"}


def find_seqinfo(entries: list[TreeEntry], match_id: str, half_tokens: list[str]) -> str | None:
    cands = [e for e in files_for_match(entries, match_id) if e.name == "seqinfo.ini"]
    if not cands:
        return None
    half = [e for e in cands if _has_half_token(e.path, half_tokens)]
    return (half or cands)[0].path


def find_video(
    entries: list[TreeEntry], match_id: str, half_tokens: list[str], exts: list[str]
) -> dict | None:
    cands = [
        e for e in files_for_match(entries, match_id)
        if any(e.name.lower().endswith(x) for x in exts)
    ]
    if not cands:
        return None
    half = [e for e in cands if _has_half_token(e.path, half_tokens)]
    if half:
        e = max(half, key=lambda x: x.size)
        return {"path": e.path, "size": e.size, "lfs_sha256": e.lfs_sha256, "scope": "per_half"}
    other_half = [e for e in cands if _has_half_token(e.path, ["2nd", "second", "half2", "half_2", "h2"])]
    rest = [e for e in cands if e not in other_half]
    if not rest:
        return None
    e = max(rest, key=lambda x: x.size)
    return {"path": e.path, "size": e.size, "lfs_sha256": e.lfs_sha256, "scope": "full_match"}


def find_gsr(entries: list[TreeEntry], match_id: str, half_tokens: list[str]) -> str | None:
    cands = [
        e for e in files_for_match(entries, match_id)
        if e.name.lower().endswith(".json") and "gsr" in e.path.lower()
    ]
    if not cands:
        return None
    half = [e for e in cands if _has_half_token(e.path, half_tokens)]
    return (half or cands)[0].path


def plan_download(entries: list[TreeEntry], match_id: str, cfg: dict) -> dict:
    """Narrowest exact-path plan for one match/half (GT + seqinfo + GSR + video)."""
    tokens = list(cfg["half_tokens"])
    gt = find_gt(entries, match_id, tokens)
    video = find_video(entries, match_id, tokens, list(cfg["video_exts"]))
    seqinfo = find_seqinfo(entries, match_id, tokens)
    gsr = find_gsr(entries, match_id, tokens)
    files = [p for p in (
        gt["path"] if gt else None, seqinfo, gsr, video["path"] if video else None
    ) if p]
    size_by = {e.path: e.size for e in entries}
    return {
        "match_id": match_id,
        "gt": gt,
        "seqinfo": seqinfo,
        "gsr": gsr,
        "video": video,
        "files": files,
        "total_bytes": int(sum(size_by.get(p, 0) for p in files)),
        "video_bytes": int(video["size"]) if video else 0,
    }


def layout_inventory(entries: list[TreeEntry]) -> dict:
    by_top: dict[str, dict] = {}
    by_match: dict[str, int] = {}
    for e in entries:
        t = by_top.setdefault(e.top or "<root>", {"files": 0, "bytes": 0})
        t["files"] += 1
        t["bytes"] += e.size
        for m in match_ids_in_path(e.path):
            by_match[m] = by_match.get(m, 0) + e.size
    return {
        "n_files": len(entries),
        "total_bytes": int(sum(e.size for e in entries)),
        "by_top_level": by_top,
        "match_ids_seen": sorted(by_match),
        "bytes_by_match": dict(sorted(by_match.items())),
    }


# ----------------------------------------------------------------- live hub


def resolve_tree(repo_id: str, repo_type: str, revision: str, token: str | None):
    """Return (commit_sha, entries) for the live repository."""
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    info = api.repo_info(repo_id, repo_type=repo_type, revision=revision)
    sha = getattr(info, "sha", None) or revision
    items = list(
        api.list_repo_tree(repo_id, repo_type=repo_type, revision=sha, recursive=True, expand=True)
    )
    return sha, entries_from_tree(items)


def check_access(repo_id: str, repo_type: str, token: str | None) -> dict:
    """Classify access: ok / gated_no_access / not_found / unauthenticated."""
    from huggingface_hub import HfApi
    from huggingface_hub.errors import GatedRepoError, RepositoryNotFoundError

    api = HfApi(token=token)
    try:
        api.auth_check(repo_id, repo_type=repo_type)
        return {"status": "ok"}
    except GatedRepoError as exc:
        return {"status": "gated_no_access", "detail": str(exc)[:300]}
    except RepositoryNotFoundError as exc:
        return {"status": "not_found_or_unauthenticated", "detail": str(exc)[:300]}
    except Exception as exc:  # pragma: no cover - network dependent
        return {"status": "error", "detail": f"{type(exc).__name__}: {str(exc)[:300]}"}


def dry_run(repo_id: str, repo_type: str, revision: str, patterns: list[str], token: str | None) -> list[dict]:
    from huggingface_hub import snapshot_download

    infos = snapshot_download(
        repo_id=repo_id, repo_type=repo_type, revision=revision, token=token,
        allow_patterns=patterns, dry_run=True,
    )
    out = []
    for i in infos or []:
        d = asdict(i) if hasattr(i, "__dataclass_fields__") else dict(vars(i))
        out.append({k: (str(v) if not isinstance(v, int | float | bool | str | type(None)) else v)
                    for k, v in d.items()})
    return out


def download(
    repo_id: str, repo_type: str, revision: str, patterns: list[str],
    local_dir: Path, token: str | None, forbidden: list[str],
) -> Path:
    assert_not_forbidden(patterns, forbidden)
    from huggingface_hub import snapshot_download

    path = snapshot_download(
        repo_id=repo_id, repo_type=repo_type, revision=revision, token=token,
        allow_patterns=patterns, local_dir=str(local_dir), max_workers=4,
    )
    return Path(path)
