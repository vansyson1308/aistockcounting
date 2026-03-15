#!/usr/bin/env bash
set -euo pipefail

cd backend
ruff check app tests
black --check app tests
pytest -q --cov=app --cov-report=term-missing --cov-fail-under=80
