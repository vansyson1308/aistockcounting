"""Secret access + redaction. Secrets are never printed or serialized.

Resolution order: process environment → Kaggle `UserSecretsClient` (when the
`kaggle_secrets` module exists). Missing secrets return None; callers decide
whether that is a blocker (HF_TOKEN) or optional (GH_PAT).
"""

from __future__ import annotations

import os
import re

_PATTERNS = [
    re.compile(r"hf_[A-Za-z0-9]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"gho_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(token|secret|password|authorization)(\"?\s*[:=]\s*\"?)([^\s\"',}]{8,})"),
]


def get_secret(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value.strip() or None
    try:  # pragma: no cover - only importable inside Kaggle
        from kaggle_secrets import UserSecretsClient  # type: ignore

        value = UserSecretsClient().get_secret(name)
        return value.strip() if value else None
    except Exception:
        return None


def redact(text: str) -> str:
    """Mask token-like substrings so logs/reports never leak credentials."""
    out = text
    for pat in _PATTERNS[:-1]:
        out = pat.sub("<REDACTED>", out)
    out = _PATTERNS[-1].sub(lambda m: f"{m.group(1)}{m.group(2)}<REDACTED>", out)
    return out


def redact_obj(obj):
    """Recursively redact strings inside JSON-like structures."""
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [redact_obj(v) for v in obj]
    return obj


def describe_presence(names: tuple[str, ...] = ("HF_TOKEN", "GH_PAT")) -> dict:
    """Booleans only — safe to print."""
    return {n: get_secret(n) is not None for n in names}
