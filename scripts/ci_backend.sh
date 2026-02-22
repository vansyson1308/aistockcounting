#!/usr/bin/env bash
set -euo pipefail

cd backend
ruff check app tests
black --check app tests
pytest -q
