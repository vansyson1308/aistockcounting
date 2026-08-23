"""Repo-root pytest conftest: make `ml` and `tools` importable.

Only loaded when pytest runs with the repository root as rootdir (the ml/
and camsim test suites). The backend suite runs with `cd backend` and never
loads this file.
"""

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
